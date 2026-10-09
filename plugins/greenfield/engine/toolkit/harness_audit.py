"""Measure a repository's coding-agent harness: its context weight, its false claims and its gates.

What loads into an agent's context, what the docs claim that the tree does not hold, and what the gates cost
and repeat. Standard library only; no model calls.

Usage:
  python harness_audit.py                      # full report (markdown to stdout)
  python harness_audit.py --json report.json --md report.md --since "7 days ago"
  python harness_audit.py --baseline last.json # adds deltas against an earlier report
  python harness_audit.py --time-hooks         # also times every Claude Code and git hook (temp worktree)
  python harness_audit.py --gate               # cheap budget checks only; exit 1 on a breach (commit hook)
  python harness_audit.py --transcripts ~/.claude/projects/<slug>   # agent and skill use from session logs

Configuration: harness.toml at the root, or [tool.harness] in pyproject.toml. Every key has a default.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import time
import tomllib
from collections import Counter, defaultdict
from pathlib import Path

DEFAULTS = {
    "exclude": [
        "vendor/*",
        ".venv/*",
        "node_modules/*",
        "*/node_modules/*",
        ".claude/worktrees/*",
        ".git/*",
        "*/.pytest_cache/*",
        ".pytest_cache/*",
        "web/src/generated/*",
        "dist/*",
        "build/*",
    ],
    "code_dirs": ["src", "tools", "tests", "infra", "migrations", "web/src", "app", "lib"],
    "instruction_files": [
        "AGENTS.md",
        "CLAUDE.md",
        ".claude/CLAUDE.md",
        "CLAUDE.local.md",
        ".claude/AGENTS.md",
    ],
    "dup_exclude": [],
    "phantom_ignore": [],
    "path_aliases": {},
    "phantom_bare_names": False,
    "terms_ignore": [],
    "since": "7 days ago",
    "shingle_words": 12,
    "dup_min_shingles": 12,
    "term_min_mentions": 5,
    "samples": {},
    "budgets": {
        "always_loaded_bytes": 10000,
        "mandated_read_bytes": 20000,
        "doc_bytes": 12000,
        "description_chars": 400,
        "edit_hook_seconds": 1.0,
        "bash_hook_seconds": 0.2,
        "commit_hook_seconds": 10.0,
        "docs_only_commit_share": 0.15,
        "check_stages": 2,
    },
    "caps": {},
}
# Config keys whose list values extend the defaults instead of replacing them.
EXTENDING_KEYS = ("exclude", "phantom_ignore", "terms_ignore", "dup_exclude")

# A shingle shared by two to four docs is copied text; one shared by more is boilerplate.
SHARED_MIN_DOCS = 2
SHARED_MAX_DOCS = 4
# A capitalised word shorter than this is not counted as a name.
MIN_TERM_LENGTH = 3
# Below this many commits in the window, a share of commits says nothing.
MIN_COMMITS = 5
# A doc changed in at least this share of the window's commits is holding state.
CHURN_SHARE = 0.4
# This many dates, amounts, revisions or ids in a loaded doc make it a ledger.
PROSE_STATE_MIN = 5
# Each Claude Code hook is run this many times and its median kept.
TIMING_RUNS = 3
HOOK_TIMEOUT_SECONDS = 900

# An instruction to read: the verb opens a clause ("Read X", "then X", "first, read X"), not "a read-only
# store".
READ_IMPERATIVE = re.compile(
    r"(?:^|[.!?;:]\s+|,\s*|\bthen\s+|\bfirst\s+|\balways\s+)(?:read|start with|open)\b(?!-)",
    re.IGNORECASE | re.MULTILINE,
)
# A read that applies only to some work is conditional; one before any work ("before changing anything") is
# not.
CONDITIONAL = re.compile(
    r"\b(?:if|when|whenever|touch(?:ing)?|you touch|for the area|relying|"
    r"before (?!(?:changing |doing |starting |touching )?anything\b)\w+ing)\b",
    re.IGNORECASE,
)
# A condition that governs every read in its sentence: one leading the verb, or a trailing before/when/if
# clause.
GOVERNING = re.compile(r"\b(?:before|when|whenever|if)\b", re.IGNORECASE)
MD_LINK = re.compile(r"\]\(([^)\s]+)\)")
CODE_SPAN = re.compile(r"`([^`\n]+)`")
PATHISH = re.compile(r"^[\w.@+\-/]+\.(?:py|md|toml|json|sh|sql|ya?ml|ts|tsx|js|cjs|mjs|txt|cfg|ini)$")
DOTTED_ID = re.compile(r"^[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)+(?:\(\))?$")
SNAKE_ID = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+(?:\(\))?$")
PROSE_STATE = {
    "date": re.compile(r"\b20\d\d-\d\d-\d\d\b"),
    "money": re.compile(
        r"\$\d|\b\d+(?:\.\d+)? ?(?:cents?|¢)|\b(?:one|two|three|four|five|ten|forty[- ]\w+) cents\b",
        re.IGNORECASE,
    ),
    "revision": re.compile(r"\brevision \d+\b", re.IGNORECASE),
    "uuid": re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"),
}
SIGNATURES = {
    "pytest": re.compile(r"\bpytest\b"),
    "ruff check": re.compile(r"\bruff check\b"),
    "ruff format": re.compile(r"\bruff format\b"),
    "project check": re.compile(
        r"(?:python[0-9.]*|uv run(?: python)?)\s+\S*tools/check\.py|\bmake check\b|\bjust check\b"
    ),
    "import contracts": re.compile(r"\blint-imports\b|import[-_]linter"),
    "type check": re.compile(r"\b(?:pyrefly|mypy|pyright|tsc)\b"),
    "js lint": re.compile(r"\bbiome\b|\beslint\b"),
    "js boundaries": re.compile(r"\bdepcruise\b|dependency-cruiser"),
}
# Capitalised words that are ordinary English or common product names, never a project's own term.
COMMON_CAPS = {
    *("The", "This", "That", "These", "Those", "When", "What", "Where", "Which", "While", "With"),
    *("Without", "Each", "Every", "Some", "None", "Never", "Always", "Only", "And", "But", "For", "From"),
    *("Into", "Once", "Then", "There", "Their", "They", "Your", "You", "Our", "Its", "It's", "Use", "Run"),
    *("See", "Read", "Keep", "Add", "Make", "Set", "Note", "Notes", "Do", "Does", "Not", "No", "Yes", "If"),
    *("Else", "Also", "After", "Before", "Until", "Unless", "Because", "Since", "Here", "How", "Why"),
    *("Who", "All", "Any", "Most", "More", "Less", "One", "Two", "Three", "First", "Second", "Last"),
    *("Next", "New", "Old", "Done", "Open", "Closed", "True", "False", "Python", "JSON", "SQL", "API"),
    *("CLI", "HTTP", "HTTPS", "URL", "MCP", "SDK", "Markdown", "GitHub", "Claude", "Code", "Anthropic"),
    *("OpenAI", "README", "TODO", "OK", "Mac", "Linux", "Windows", "CI"),
}
EVENT_STAGES = {"SessionStart": "session", "UserPromptSubmit": "prompt", "Stop": "stop"}
TOOL_EVENTS = ("PreToolUse", "PostToolUse")
GIT_HOOK_STAGES = {
    "pre-commit": "commit",
    "pre-merge-commit": "commit",
    "commit-msg": "commit",
    "pre-push": "push",
}
WHOLE_PROJECT_CHECKS = ("project check", "pytest", "import contracts", "type check")
TOOL_USE_NAME = re.compile(r'"subagent_type"\s*:\s*"([^"]+)"|"skill"\s*:\s*"([^"]+)"')


def load_config(root: Path, explicit: Path | None = None) -> dict:
    """The defaults overlaid with harness.toml, [tool.harness] in pyproject.toml, or an explicit file."""
    cfg = json.loads(json.dumps(DEFAULTS))
    raw = {}
    if explicit:
        raw = tomllib.loads(explicit.read_text()).get("harness", {})
    elif (root / "harness.toml").exists():
        raw = tomllib.loads((root / "harness.toml").read_text()).get("harness", {})
    elif (root / "pyproject.toml").exists():
        raw = tomllib.loads((root / "pyproject.toml").read_text()).get("tool", {}).get("harness", {})
    for key, value in raw.items():
        if isinstance(value, dict) and isinstance(cfg.get(key), dict):
            cfg[key].update(value)
        elif key in EXTENDING_KEYS and isinstance(value, list):
            cfg[key] = cfg[key] + value
        else:
            cfg[key] = value
    return cfg


def git(root: Path, *args: str, check: bool = False) -> str:
    """The stdout of a git command run in the repository, or an empty string when it fails."""
    done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=check)
    return done.stdout if done.returncode == 0 else ""


def excluded(rel: str, patterns: list[str]) -> bool:
    """Whether a relative path matches any of the glob patterns."""
    return any(fnmatch.fnmatch(rel, p) for p in patterns)


def list_files(root: Path, cfg: dict) -> list[str]:
    """Every file git would track (or every file, outside git), less the configured exclusions."""
    listed = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z").split("\0")
    if not any(listed):
        listed = [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()]
    return sorted({f for f in listed if f and not excluded(f, cfg["exclude"]) and (root / f).is_file()})


def read(path: Path) -> str:
    """The file's text, or an empty string when it cannot be read."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def frontmatter_field(text: str, field: str) -> str:
    """A field's value from a document's YAML frontmatter, folded when it is a block scalar."""
    if not text.startswith("---"):
        return ""
    head = text.split("\n---", 2)[0]
    lines = head.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(f"{field}:"):
            value = line.split(":", 1)[1].strip()
            if value in {">", "|", ">-", "|-", ""}:
                value = " ".join(x.strip() for x in lines[i + 1 :] if x.startswith((" ", "\t")))
            return value.strip("'\"")
    return ""


def finding(lens: str, key: str, severity: str, message: str, *, evidence: list | None = None) -> dict:
    """One finding, identified by a stable hash of its lens and key."""
    fid = hashlib.sha1(f"{lens}|{key}".encode(), usedforsecurity=False).hexdigest()[:10]
    return {
        "id": fid,
        "lens": lens,
        "key": key,
        "severity": severity,
        "message": message,
        "evidence": evidence or [],
    }


# ---------------------------------------------------------------- lens 1: context weight
def resolve_ref(root: Path, src: Path, target: str) -> Path | None:
    """The existing file a reference names, relative to its document or to the root, if there is one."""
    target = target.split("#", 1)[0].strip()
    if not target or re.match(r"^[a-z]+:", target) or target.startswith(("~", "$", "<")):
        return None
    for base in (src.parent, root):
        candidate = (base / target.lstrip("./") if target.startswith("./") else base / target).resolve()
        if candidate.exists():
            return candidate
    return None


def mandated_targets(root: Path, path: Path) -> list[tuple[Path, bool]]:
    """Files a document instructs the agent to read, each with whether the instruction is conditional.

    A sentence counts when a read verb opens one of its clauses. Its own links count, and so do links
    elsewhere in the paragraph whose link text the sentence names ("read the status page" with
    [status page](...) one sentence earlier). Table rows never mandate anything: a "where to read" table is
    navigation.
    """
    found = []
    text = "\n".join(line for line in read(path).splitlines() if not line.lstrip().startswith("|"))
    for paragraph in re.split(r"\n\s*\n|\n\s*[-*]\s+", text):
        links = re.findall(r"\[([^\]]+)\]\(([^)\s]+)\)", paragraph)
        # A semicolon starts an independent clause.
        for sentence in re.split(r"(?<=[.!?])\s+|;\s*", paragraph):
            verb = READ_IMPERATIVE.search(sentence)
            if not verb:
                continue
            refs = _sentence_refs(sentence, links)
            if not refs:
                continue
            last = max(at for _, at in refs)
            tail = sentence[last:].split(")", 1)[-1].split("`", 1)[-1]
            lead, trailing = sentence[: verb.start()], tail if GOVERNING.search(tail) else ""
            governed = bool(CONDITIONAL.search(lead) or CONDITIONAL.search(trailing))
            clauses = [(m.start(), m.end()) for m in re.finditer(r"[^,;]+?(?=,|;|\band\b|$)", sentence)]
            for ref, at in refs:
                clause = next((sentence[a:b] for a, b in clauses if a <= at < b), "")
                conditional = governed or bool(CONDITIONAL.search(clause))
                hit = resolve_ref(root, path, ref)
                if hit and hit.suffix == ".md" and hit.is_file() and hit != path.resolve():
                    found.append((hit, conditional))
    return found


def _sentence_refs(sentence: str, links: list[tuple[str, str]]) -> list[tuple[str, int]]:
    """References a sentence makes, each with its position, or where the sentence names a paragraph link."""
    refs = []
    for label, ref in links:
        at = sentence.find(f"]({ref})")
        if at < 0 and label.lower() in sentence.lower():
            at = sentence.lower().find(label.lower())
        if at >= 0:
            refs.append((ref, at))
    spans = CODE_SPAN.finditer(sentence)
    return refs + [(m.group(1), m.start()) for m in spans if m.group(1).endswith(".md")]


def _always_loaded(root: Path, instruction_files: list[str]) -> list[Path]:
    """Instruction files, their @-imports, and unscoped rules: what every session loads."""
    always = []
    for name in instruction_files:
        p = root / name
        if not p.is_file():
            continue
        always.append(p)
        for imp in re.findall(r"(?m)^\s*@([\w./\-]+)", read(p)):  # CLAUDE.md imports
            hit = resolve_ref(root, p, imp)
            if hit and hit.is_file():
                always.append(hit)
    rules = sorted((root / ".claude/rules").glob("**/*.md")) if (root / ".claude/rules").is_dir() else []
    return always + [r for r in rules if not frontmatter_field(read(r), "paths")]


def _descriptions(root: Path, limit: int) -> tuple[list[dict], list[dict]]:
    """Each skill and agent description's length, and a finding for each one over the limit."""
    descriptions, findings = [], []
    for kind, pattern in (("skill", ".claude/skills/*/SKILL.md"), ("agent", ".claude/agents/*.md")):
        for p in sorted(root.glob(pattern)):
            desc = frontmatter_field(read(p), "description")
            name = frontmatter_field(read(p), "name") or p.parent.name if kind == "skill" else p.stem
            descriptions.append({"kind": kind, "name": name, "chars": len(desc)})
            if len(desc) > limit:
                findings.append(
                    finding(
                        "context",
                        f"desc:{kind}:{name}",
                        "low",
                        f"{kind} '{name}' description is {len(desc)} chars (budget {limit}); "
                        "it loads into every session",
                    )
                )
    return descriptions, findings


def _mandated_reads(root: Path, always: list[Path]) -> dict:
    """Docs the always-loaded files tell the agent to read, two hops deep, each with its size and source."""
    mandated, frontier = {}, [(p, False) for p in set(always)]
    for _ in range(2):  # two hops: an instruction file's reads, and what those tell the agent to read
        frontier = _follow_reads(root, frontier, always, mandated)
    return mandated


def _follow_reads(
    root: Path, frontier: list[tuple[Path, bool]], always: list[Path], mandated: dict
) -> list[tuple[Path, bool]]:
    """Record the reads the frontier mandates, and return the newly mandated docs as the next frontier."""
    nxt = []
    for src, src_conditional in frontier:
        for t, own_conditional in mandated_targets(root, src):
            rel, conditional = str(t.relative_to(root)), own_conditional or src_conditional
            if t in always or (rel in mandated and (conditional or not mandated[rel]["conditional"])):
                continue
            mandated[rel] = {
                "bytes": t.stat().st_size,
                "from": str(src.relative_to(root)),
                "conditional": conditional,
            }
            nxt.append((t, conditional))
    return nxt


def _oversized_docs(
    root: Path, cfg: dict, files: list[str], *, mandated: dict, always: list[Path]
) -> list[dict]:
    """A finding for each doc over its size cap; high when the doc loads or is mandated before work."""
    findings, budgets, caps = [], cfg["budgets"], cfg["caps"]
    for rel in files:
        if not rel.endswith(".md") or rel.startswith((".claude/agents/", ".claude/skills/")):
            continue
        size, cap = (root / rel).stat().st_size, caps.get(rel, budgets["doc_bytes"])
        if size > cap:
            hot = (rel in mandated and not mandated[rel]["conditional"]) or root / rel in always
            findings.append(
                finding(
                    "context",
                    f"doc:{rel}",
                    "high" if hot else "medium",
                    f"{rel} is {size:,} bytes (cap {cap:,}){' and is mandated reading' if hot else ''}",
                )
            )
    return findings


def _nested_instruction_files(files: list[str]) -> list[dict]:
    """A finding for each instruction file below the root, which loads whenever its directory is read."""
    nested = [
        f
        for f in files
        if Path(f).name in {"AGENTS.md", "CLAUDE.md"} and "/" in f and not f.startswith(".claude/")
    ]
    return [
        finding(
            "context",
            f"nested:{f}",
            "medium",
            f"{f} is injected whenever the agent reads a file under {Path(f).parent}/",
        )
        for f in nested
    ]


def _worktree_copies(root: Path) -> list[dict]:
    """A finding when worktrees under .claude hold their own copies of the instruction files."""
    wt = root / ".claude/worktrees"
    copies = (
        sorted(str(p.relative_to(root)) for p in wt.glob("*/AGENTS.md"))
        + sorted(str(p.relative_to(root)) for p in wt.glob("*/CLAUDE.md"))
        if wt.is_dir()
        else []
    )
    if not copies:
        return []
    return [
        finding(
            "context",
            "worktree_copies",
            "medium",
            f"{len(copies)} worktree instruction copies: "
            "a session inside a worktree also loads the root copy",
            evidence=copies,
        )
    ]


def lens_context(root: Path, cfg: dict, files: list[str]) -> tuple[dict, list]:
    """Lens 1: the bytes every session loads, the reading it mandates before work, and oversized docs."""
    budgets = cfg["budgets"]
    always = _always_loaded(root, cfg["instruction_files"])
    descriptions, findings = _descriptions(root, budgets["description_chars"])
    always_bytes = sum(p.stat().st_size for p in set(always)) + sum(d["chars"] for d in descriptions)
    out: dict = {
        "always_loaded": sorted({str(p.relative_to(root)) for p in always}),
        "always_loaded_bytes": always_bytes,
        "descriptions": descriptions,
    }
    if always_bytes > budgets["always_loaded_bytes"]:
        findings.append(
            finding(
                "context",
                "always_loaded",
                "high",
                f"{always_bytes:,} bytes load into every session (budget {budgets['always_loaded_bytes']:,}; "
                f"~{always_bytes // 4:,} tokens)",
                evidence=out["always_loaded"],
            )
        )
    mandated = _mandated_reads(root, always)
    mandated_bytes = sum(m["bytes"] for m in mandated.values() if not m["conditional"])
    out["conditional_read_bytes"] = sum(m["bytes"] for m in mandated.values() if m["conditional"])
    out["mandated_reads"] = mandated
    out["mandated_read_bytes"] = mandated_bytes
    out["session_start_bytes"] = always_bytes + mandated_bytes
    if mandated_bytes > budgets["mandated_read_bytes"]:
        findings.append(
            finding(
                "context",
                "mandated_reads",
                "high",
                f"instruction files mandate {mandated_bytes:,} bytes of reading before work (budget "
                f"{budgets['mandated_read_bytes']:,})",
                evidence=[
                    f"{k} ({v['bytes']:,} B, from {v['from']})"
                    for k, v in mandated.items()
                    if not v["conditional"]
                ],
            )
        )
    findings += _oversized_docs(root, cfg, files, mandated=mandated, always=always)
    findings += _nested_instruction_files(files)
    findings += _worktree_copies(root)
    return out, findings


# ---------------------------------------------------------------- lens 2: phantom references
def _ref_candidate(raw: str, kind: str) -> str | None:
    """A reference cleaned of its anchor and trailing punctuation, or None when it cannot name a path."""
    ref = raw.strip().split("#", 1)[0].rstrip(":,.")
    if (
        not ref
        or re.match(r"^[a-z]+:", ref)
        or any(c in ref for c in "<>*{}$~ ")
        or ref.startswith(("-", "@", "/"))
    ):
        return None
    if kind == "code" and not PATHISH.match(ref):
        return None
    return ref


def _apply_aliases(ref: str, aliases: dict) -> str:
    """The reference with each configured path alias prefix replaced by its target, in order."""
    for alias, target in aliases.items():
        if ref.startswith(alias):
            ref = target + ref[len(alias) :]
    return ref


def _is_phantom(root: Path, src: Path, ref: str, cfg: dict, *, names: set[str], suffixes: set[str]) -> bool:
    """Whether a reference names a path that exists nowhere in the tree."""
    if excluded(ref, cfg["phantom_ignore"]) or resolve_ref(root, src, ref):
        return False
    if "/" not in ref and (ref in names or not cfg["phantom_bare_names"]):
        return False
    # A path relative to a package or a vendored tree is not a phantom.
    return not any(s.endswith("/" + ref.lstrip("./")) for s in suffixes)


def _file_phantoms(root: Path, cfg: dict, rel: str, *, names: set[str], suffixes: set[str]) -> list[str]:
    """The paths one document names, in links or code spans, that do not exist."""
    src, missing = root / rel, []
    text = read(src)
    refs = [(m, "link") for m in MD_LINK.findall(text)] + [(m, "code") for m in CODE_SPAN.findall(text)]
    for raw, kind in refs:
        ref = _ref_candidate(raw, kind)
        if ref is None:
            continue
        ref = _apply_aliases(ref, cfg["path_aliases"])
        if _is_phantom(root, src, ref, cfg, names=names, suffixes=suffixes):
            missing.append(ref)
    return missing


def _git_ignored(root: Path, paths: set[str]) -> set[str]:
    """The paths git ignores: a missing ignored path is a build output, not a phantom."""
    done = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "--no-index", "--stdin"],
        input="\n".join(paths),
        capture_output=True,
        text=True,
        check=False,
    )
    return set(done.stdout.split())


def lens_phantoms(root: Path, cfg: dict, files: list[str], hot: set[str]) -> tuple[dict, list]:
    """Lens 2: paths the docs and harness files name that do not exist in the tree."""
    every = [f for f in git(root, "ls-files", "-z").split("\0") if f] or files  # vendored trees included
    names = {Path(f).name for f in every}
    suffixes = {f"/{f}" for f in every} | set(every)
    per_file = {}
    scan = [f for f in files if f.endswith(".md") or f.startswith((".claude/", "tools/git_hooks/"))]
    for rel in scan:
        missing = _file_phantoms(root, cfg, rel, names=names, suffixes=suffixes)
        if missing:
            per_file[rel] = sorted(set(missing))
    ignored = _git_ignored(root, {m for v in per_file.values() for m in v})
    per_file = {rel: [m for m in v if m not in ignored] for rel, v in per_file.items()}
    per_file = {rel: v for rel, v in per_file.items() if v}
    findings = [
        finding(
            "truth",
            f"phantom:{rel}",
            "high" if rel in hot else "medium",
            f"{rel} names {len(missing)} path(s) that do not exist",
            evidence=missing[:12],
        )
        for rel, missing in per_file.items()
    ]
    return {"phantom_paths": per_file, "phantom_count": sum(len(v) for v in per_file.values())}, findings


# ---------------------------------------------------------------- lens 3: duplication
def _shingles(
    root: Path, cfg: dict, docs: list[str]
) -> tuple[defaultdict[bytes, set[str]], dict[bytes, str]]:
    """The docs holding each run of words outside code blocks, keyed by hash, with one sample of each run."""
    k, seen, sample = cfg["shingle_words"], defaultdict(set), {}
    for rel in docs:
        if excluded(rel, cfg["dup_exclude"]):
            continue
        prose = re.sub(r"```.*?```", " ", read(root / rel), flags=re.DOTALL)
        words = re.findall(r"[a-z0-9']+", prose.lower())
        for i in range(len(words) - k + 1):
            shingle = " ".join(words[i : i + k])
            h = hashlib.blake2b(shingle.encode(), digest_size=8).digest()
            seen[h].add(rel)
            sample.setdefault(h, shingle)
    return seen, sample


def _ordered_pairs(owners: set[str]) -> list[tuple[str, str]]:
    """Every pair of distinct owners, each once, smaller name first."""
    return [(a, b) for a in owners for b in owners if a < b]


def lens_duplication(root: Path, cfg: dict, docs: list[str]) -> tuple[dict, list]:
    """Lens 3: pairs of docs that share long runs of identical text."""
    seen, sample = _shingles(root, cfg, docs)
    pairs, example = Counter(), {}
    for h, owners in seen.items():
        if SHARED_MIN_DOCS <= len(owners) <= SHARED_MAX_DOCS:
            for pair in _ordered_pairs(owners):
                pairs[pair] += 1
                example.setdefault(pair, sample[h])
    top = [(a, b, n) for (a, b), n in pairs.most_common() if n >= cfg["dup_min_shingles"]]
    findings = [
        finding(
            "duplication",
            f"dup:{a}|{b}",
            "medium",
            f"{a} and {b} share ~{n + cfg['shingle_words'] - 1} words of identical text",
            evidence=[f'e.g. "{example[a, b]}"'],
        )
        for a, b, n in top[:25]
    ]
    return {"duplicate_pairs": [{"a": a, "b": b, "shared_shingles": n} for a, b, n in top]}, findings


# ---------------------------------------------------------------- lens 4: names with no code
def _code_corpus(root: Path, code_dirs: list[str], files: list[str]) -> str:
    """The lowercased text of every non-markdown file under the code directories."""
    code = [
        f
        for f in files
        if any(f.startswith(d.rstrip("/") + "/") for d in code_dirs) and not f.endswith(".md")
    ]
    return "\n".join(read(root / f) for f in code).lower()


def _code_identifiers(text: str) -> list[str]:
    """The dotted or snake_case identifiers a document names in code spans, file paths aside."""
    spans = (raw.strip().rstrip("()") for raw in CODE_SPAN.findall(text))
    return [s for s in spans if (DOTTED_ID.match(s) or SNAKE_ID.match(s)) and not PATHISH.match(s)]


def _prose_sentences(text: str) -> list[str]:
    """A document's sentences with links, code spans, and heading, list and table markers removed."""
    prose = CODE_SPAN.sub(" ", MD_LINK.sub(" ", text))
    lines = (re.sub(r"^\s*(?:#+|[-*]|\d+\.|\|)\s*", "", line) for line in prose.splitlines())
    return [sentence for line in lines for sentence in re.split(r"(?<=[.!?:;|])\s+", line)]


def lens_unbuilt(root: Path, cfg: dict, files: list[str], docs: list[str]) -> tuple[dict, list]:
    """Lens 4: identifiers and capitalised terms the docs name that appear nowhere in code."""
    corpus = _code_corpus(root, cfg["code_dirs"], files)
    if not corpus:
        return {"note": "no code directories found"}, []
    ids, caps, lower = Counter(), Counter(), Counter()
    where = defaultdict(set)
    for rel in docs:
        text = read(root / rel)
        for span in _code_identifiers(text):
            ids[span] += 1
            where[span].add(rel)
        for sentence in _prose_sentences(text):
            words = re.findall(r"[A-Za-z][A-Za-z0-9]+", sentence)
            named = [w for w in words[1:] if w[0].isupper() and len(w) >= MIN_TERM_LENGTH]
            caps.update(named)
            for w in named:
                where[w].add(rel)
            lower.update(w for w in words if w.islower())
    ignore = COMMON_CAPS | set(cfg["terms_ignore"])
    unbuilt_ids = {i: n for i, n in ids.items() if i.lower() not in corpus}
    terms = {
        w: n
        for w, n in caps.items()
        if n >= cfg["term_min_mentions"]
        and w not in ignore
        and lower[w.lower()] < n
        and w.lower() not in corpus
    }
    findings = [
        finding(
            "unbuilt",
            f"term:{w}",
            "info",
            f"'{w}' appears {n}x in {len(where[w])} doc(s) and nowhere in code: unbuilt design, "
            "or a name to state when built",
            evidence=sorted(where[w])[:6],
        )
        for w, n in sorted(terms.items(), key=lambda x: -x[1])[:20]
    ]
    if unbuilt_ids:
        findings.append(
            finding(
                "unbuilt",
                "identifiers",
                "medium",
                f"{len(unbuilt_ids)} code-style identifiers in docs exist nowhere in code",
                evidence=[
                    f"{i} ({', '.join(sorted(where[i])[:2])})"
                    for i in sorted(unbuilt_ids, key=lambda x: -unbuilt_ids[x])[:15]
                ],
            )
        )
    return {"unbuilt_terms": terms, "unbuilt_identifiers": unbuilt_ids}, findings


# ---------------------------------------------------------------- lens 5: state in prose
def _is_doc(path: str) -> bool:
    """Whether a path is a markdown document."""
    return path.endswith(".md")


def _commit_files(root: Path, since: str) -> list[list[str]]:
    """The files each commit in the window changed."""
    log = git(root, "log", f"--since={since}", "--name-only", "--format=\x01%H")
    commits = [c.strip().splitlines() for c in log.split("\x01") if c.strip()]
    return [[f for f in c[1:] if f] for c in commits]


def _prose_state(root: Path, hot: set[str]) -> tuple[dict, list]:
    """Dates, amounts, revisions and ids in each hot doc, and a finding for each doc that holds many."""
    hits, findings = {}, []
    for rel in sorted(hot):
        text = read(root / rel)
        counts = {k: len(p.findall(text)) for k, p in PROSE_STATE.items()}
        total = sum(counts.values())
        if not total:
            continue
        hits[rel] = counts
        if total >= PROSE_STATE_MIN:
            findings.append(
                finding(
                    "state",
                    f"prose_state:{rel}",
                    "medium",
                    f"{rel} (loaded or mandated) carries {total} dates, amounts, revisions or ids",
                    evidence=[f"{k}: {v}" for k, v in counts.items() if v],
                )
            )
    return hits, findings


def lens_churn(root: Path, cfg: dict, hot: set[str], since: str) -> tuple[dict, list]:
    """Lens 5: docs edited so often, or so full of dates and amounts, that they hold state."""
    out, findings = {}, []
    touched = _commit_files(root, since)
    n = len(touched)
    doc_commits = sum(1 for t in touched if any(_is_doc(f) for f in t))
    docs_only = sum(1 for t in touched if t and all(_is_doc(f) for f in t))
    churn = Counter(f for t in touched for f in set(t) if _is_doc(f))
    out.update(
        commits=n,
        doc_commits=doc_commits,
        docs_only_commits=docs_only,
        top_doc_churn=[{"file": f, "commits": c} for f, c in churn.most_common(8)],
    )
    share = cfg["budgets"]["docs_only_commit_share"]
    if n >= MIN_COMMITS and docs_only / n > share:
        findings.append(
            finding(
                "state",
                "docs_only_share",
                "medium",
                f"{docs_only} of {n} commits since {since} change only docs ({docs_only / n:.0%}; budget "
                f"{share:.0%})",
            )
        )
    findings += [
        finding(
            "state",
            f"churn:{f}",
            "medium",
            f"{f} changed in {c} of {n} commits: "
            "a doc edited this often is holding state (a diary, a ledger)",
        )
        for f, c in churn.most_common(5)
        if n >= MIN_COMMITS and c / n >= CHURN_SHARE
    ]
    out["prose_state"], prose_findings = _prose_state(root, hot)
    return out, findings + prose_findings


# ---------------------------------------------------------------- lens 6: gate cost and repetition
def _settings_hooks(path: Path) -> dict:
    """The hooks table of a Claude Code settings file; empty when the file is absent or not JSON."""
    if not path.is_file():
        return {}
    try:
        settings = json.loads(read(path))
    except json.JSONDecodeError:
        return {}
    return settings.get("hooks", {})


def _hook_stage(event: str, matcher: str) -> str:
    """The stage a hook runs at: its event, or for a tool event the kind of tool it matches."""
    if event not in TOOL_EVENTS:
        return EVENT_STAGES.get(event, event)
    if re.search(r"Edit|Write", matcher):
        return "edit"
    if "Bash" in matcher:
        return "bash"
    return matcher or "tool"


def _group_entries(settings: str, event: str, group: dict) -> list[dict]:
    """The command hooks of one matcher group, each with its stage."""
    entries = []
    matcher = group.get("matcher", "")
    for h in group.get("hooks", []):
        if h.get("type") != "command":
            continue
        stage = _hook_stage(event, matcher)
        asynchronous = bool(h.get("async") or h.get("asyncRewake"))
        entries.append(
            {
                "source": settings,
                "event": event,
                "matcher": matcher,
                "command": h["command"],
                "stage": stage + ("-async" if asynchronous else ""),
                "async": asynchronous,
            }
        )
    return entries


def hook_entries(root: Path) -> list[dict]:
    """Every command hook in the project's Claude Code settings files."""
    entries = []
    for settings in (".claude/settings.json", ".claude/settings.local.json"):
        for event, groups in _settings_hooks(root / settings).items():
            for group in groups:
                entries.extend(_group_entries(settings, event, group))
    return entries


def strip_comments(text: str) -> str:
    """The text without its shell-style comment lines."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def script_text(root: Path, command: str) -> str:
    """A hook command followed by the comment-free text of each repository file it names."""
    text = command
    for raw in re.findall(r"[\w$\"'{}./\-]+", command):
        token = (
            re.sub(r"[\"']", "", raw)
            .replace("${CLAUDE_PROJECT_DIR}", "")
            .replace("$CLAUDE_PROJECT_DIR", "")
            .lstrip("/")
        )
        p = root / token
        if token and p.is_file():
            text += "\n" + strip_comments(read(p))
    return text


def _signatures(body: str) -> list[str]:
    """The names of the known checks a script body runs."""
    return [name for name, rx in SIGNATURES.items() if rx.search(body)]


def _hook_name(command: str) -> str:
    """The file name of the last word of a hook command: the script it runs."""
    return Path(re.sub(r"[\"']", "", command).split()[-1]).name


def _git_hook_checks(root: Path, git_dir: Path, matrix: defaultdict[str, set[str]]) -> tuple[dict, list]:
    """The checks each git hook runs, recorded in the matrix, and a finding for each hook git would skip."""
    git_hooks, findings = {}, []
    if not git_dir.is_dir():
        return git_hooks, findings
    for p in sorted(git_dir.iterdir()):
        stage = GIT_HOOK_STAGES.get(p.name)
        if not p.is_file() or p.name.endswith(".sample") or not stage:
            continue
        if not os.access(p, os.X_OK):
            shown = p.relative_to(root) if p.is_relative_to(root) else p
            findings.append(
                finding(
                    "gates",
                    f"not_executable:{p.name}",
                    "high",
                    f"git hook {shown} is not executable, so git skips it",
                )
            )
            continue
        git_hooks[p.name] = _signatures(strip_comments(read(p)))
        for name in git_hooks[p.name]:
            matrix[name].add(stage)
    return git_hooks, findings


def _workflow_checks(root: Path, matrix: defaultdict[str, set[str]]) -> None:
    """Record in the matrix the checks each GitHub workflow runs."""
    workflows = root / ".github/workflows"
    for wf in sorted(workflows.glob("*.y*ml")) if workflows.is_dir() else []:
        for name in _signatures(strip_comments(read(wf))):
            matrix[name].add("ci")


def _stage_findings(matrix: defaultdict[str, set[str]], check_stages: int) -> list[dict]:
    """Findings for checks that run synchronously at too many stages, or on every edit."""
    findings = []
    for name, stages in matrix.items():
        sync = {s for s in stages if not s.endswith("-async")}
        if len(sync) > check_stages + 1:
            findings.append(
                finding(
                    "gates",
                    f"repeat:{name}",
                    "medium",
                    f"'{name}' runs synchronously at {len(sync)} stages ({', '.join(sorted(sync))}); "
                    "keep one local stage plus CI",
                    evidence=sorted(stages),
                )
            )
        if "edit" in sync and name in WHOLE_PROJECT_CHECKS:
            findings.append(
                finding(
                    "gates",
                    f"edit_whole_project:{name}",
                    "medium",
                    f"an edit hook invokes '{name}' synchronously; unless it is scoped to the edited file or "
                    "conditional, move it to commit or run it async (--time-hooks measures it)",
                )
            )
    return findings


def _self_pinning(root: Path, entries: list[dict]) -> list[dict]:
    """A finding when a tool pins a hook or the settings file by digest."""
    tools = root / "tools"
    hook_names = {_hook_name(e["command"]) for e in entries} | {"settings.json"}
    pins = [
        f"{p.relative_to(root)}: {line.strip()[:90]}"
        for p in (list(tools.rglob("*.py")) if tools.is_dir() else [])
        for line in read(p).splitlines()
        if re.search(r"\b[0-9a-f]{16,64}\b", line) and any(n and n in line for n in hook_names)
    ]
    if not pins:
        return []
    return [
        finding(
            "gates",
            "self_pinning",
            "medium",
            f"{len(pins)} gate files are pinned by digest inside a gate: every gate edit then needs a gate "
            "change. A canary (planted violation) proves a gate still refuses without freezing its file",
            evidence=pins[:8],
        )
    ]


def _slow_findings(timings: dict, budgets: dict) -> list[dict]:
    """A finding for each timed hook slower than its stage's budget."""
    findings = []
    for label, t in timings.items():
        stage = label.split(" ", 1)[0]
        limit = {
            "edit": budgets["edit_hook_seconds"],
            "bash": budgets["bash_hook_seconds"],
            "commit": budgets["commit_hook_seconds"],
        }.get(stage)
        if limit and t["median_s"] > limit:
            findings.append(
                finding(
                    "gates",
                    f"slow:{label}",
                    "high" if stage == "edit" else "medium",
                    f"{label} takes {t['median_s']:.2f}s per call (budget {limit}s) and blocks the session",
                )
            )
    return findings


def lens_gates(root: Path, cfg: dict, *, time_hooks: bool) -> tuple[dict, list]:
    """Lens 6: where each check runs, which run too often or on every edit, and what the hooks cost."""
    matrix = defaultdict(set)
    entries = hook_entries(root)
    for e in entries:
        e["checks"] = _signatures(script_text(root, e["command"]))
        for name in e["checks"]:
            matrix[name].add(e["stage"])
    hooks_path = git(root, "config", "--get", "core.hooksPath").strip()
    git_dir = root / hooks_path if hooks_path else root / ".git/hooks"
    git_hooks, findings = _git_hook_checks(root, git_dir, matrix)
    _workflow_checks(root, matrix)
    findings += _stage_findings(matrix, cfg["budgets"]["check_stages"])
    findings += _self_pinning(root, entries)
    timings = time_all(root, cfg, entries, git_dir) if time_hooks else {}
    findings += _slow_findings(timings, cfg["budgets"])
    return {
        "hooks": entries,
        "git_hooks": git_hooks,
        "check_matrix": {k: sorted(v) for k, v in matrix.items()},
        "timings": timings,
    }, findings


def _samples(cfg: dict, tracked: list[str]) -> dict:
    """The files an edit hook is timed against: configured ones, else the last source and first doc file."""
    samples = dict(cfg.get("samples", {}))
    py = next((f for f in reversed(tracked) if f.startswith("src/") and f.endswith(".py")), "")
    samples.setdefault("py", py)
    md = next((f for f in tracked if f.startswith("docs/") and f.endswith(".md")), "README.md")
    samples.setdefault("md", md)
    return samples


def _payloads(entry: dict, samples: dict, tmp: Path) -> list[tuple[str, dict]]:
    """The hook inputs a hook is timed with, each tagged with the sample it edits."""
    if entry["stage"].startswith("edit"):
        payloads = [
            (k, {"tool_name": "Edit", "tool_input": {"file_path": str(tmp / v)}})
            for k, v in samples.items()
            if v
        ]
    elif entry["stage"].startswith("bash"):
        payloads = [("ls", {"tool_name": "Bash", "tool_input": {"command": "ls"}})]
    else:
        payloads = [("", {})]
    return [
        (tag, {**payload, "session_id": "harness-audit", "hook_event_name": entry["event"]})
        for tag, payload in payloads
    ]


def _seconds(command: list[str], cwd: Path, env: dict[str, str], stdin: str | None) -> float:
    """The wall-clock seconds one run of a command takes."""
    start = time.perf_counter()
    subprocess.run(
        command,
        cwd=cwd,
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=HOOK_TIMEOUT_SECONDS,
        check=False,
    )
    return time.perf_counter() - start


def time_all(root: Path, cfg: dict, entries: list[dict], git_dir: Path) -> dict:
    """Time each hook in a throwaway worktree, so hooks that fix or render files never touch the real tree."""
    tmp = Path(tempfile.mkdtemp(prefix="harness-audit-")) / "wt"
    if not git(root, "worktree", "add", "--detach", "-q", str(tmp), "HEAD") and not tmp.exists():
        return {"error": {"median_s": 0.0, "note": "could not create a worktree"}}
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(tmp))
    if (root / ".venv").is_dir():
        env["UV_PROJECT_ENVIRONMENT"] = str(root / ".venv")  # reuse the synced environment
    samples = _samples(cfg, git(tmp, "ls-files").split())
    results = {}
    try:
        for e in entries:
            for tag, payload in _payloads(e, samples, tmp):
                stdin = json.dumps(payload)
                runs = [_seconds(["sh", "-c", e["command"]], tmp, env, stdin) for _ in range(TIMING_RUNS)]
                label = f"{e['stage']} {_hook_name(e['command'])}{' (' + tag + ')' if tag else ''}"
                results[label] = {"median_s": round(statistics.median(runs), 2)}
        for hook in ("pre-commit",):
            p = git_dir / hook
            if p.is_file() and os.access(p, os.X_OK):
                results[f"commit {hook}"] = {"median_s": round(_seconds([str(p)], tmp, env, None), 2)}
    finally:
        git(root, "worktree", "remove", "--force", str(tmp))
    return results


# ---------------------------------------------------------------- lens 7: agent and skill use
def _owns(name: str, path: str) -> bool:
    """Whether a changed path is the definition of the named agent or skill."""
    return f"/{name}/" in f"/{path}" or path.endswith(f"/{name}.md")


def _commit_uses(root: Path, since: str, names: list[str]) -> dict[str, int]:
    """How many commit messages in the window name each agent or skill, less commits that edit it."""
    commits = []  # (message, files changed): a commit that edits a definition is not a use of it
    for chunk in git(root, "log", f"--since={since}", "--name-only", "--format=\x01%B\x02").split("\x01"):
        message, _, changed = chunk.partition("\x02")
        commits.append((message, changed.split()))
    return {n: sum(1 for m, fs in commits if n in m and not any(_owns(n, f) for f in fs)) for n in names}


def _transcript_uses(transcripts: Path, names: list[str]) -> dict[str, int]:
    """How many times session transcripts invoke each agent or skill."""
    use = dict.fromkeys(names, 0)
    for log in transcripts.rglob("*.jsonl"):
        for line in read(log).splitlines():
            if '"tool_use"' not in line:
                continue
            for m in TOOL_USE_NAME.finditer(line):
                name = (m.group(1) or m.group(2)).split(":")[-1]
                if name in use:
                    use[name] += 1
    return use


def lens_usage(root: Path, since: str, transcripts: Path | None) -> tuple[dict, list]:
    """Lens 7: agents and skills nothing used in the window, by transcripts when given, else by commits."""
    agents = [p.stem for p in sorted(root.glob(".claude/agents/*.md"))]
    skills = [p.parent.name for p in sorted(root.glob(".claude/skills/*/SKILL.md"))]
    if transcripts and transcripts.is_dir():
        source, use = "session transcripts", _transcript_uses(transcripts, agents + skills)
    else:
        source, use = "commit messages", _commit_uses(root, since, agents + skills)
    findings = [
        finding(
            "usage",
            f"unused:{n}",
            "low",
            f"'{n}' was not used since {since} (by {source}); its description still loads every session",
        )
        for n, c in use.items()
        if c == 0
    ]
    return {"usage": use, "usage_source": source}, findings


# ---------------------------------------------------------------- report
def run(root: Path, cfg: dict, args: argparse.Namespace) -> dict:
    """The full report: every lens, or in gate mode only the cheap context and phantom lenses."""
    files = list_files(root, cfg)
    docs = [f for f in files if f.endswith(".md")]
    report: dict = {
        "root": str(root),
        "head": git(root, "rev-parse", "--short", "HEAD").strip(),
        "since": args.since,
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "metrics": {},
        "findings": [],
    }
    ctx, f1 = lens_context(root, cfg, files)
    hot = set(ctx["mandated_reads"]) | set(ctx["always_loaded"])
    report["context"] = ctx
    phantoms, f2 = lens_phantoms(root, cfg, files if not args.gate else sorted(hot), hot)
    report["truth"] = phantoms
    report["findings"] = f1 + f2
    report["metrics"] = {
        "always_loaded_bytes": ctx["always_loaded_bytes"],
        "mandated_read_bytes": ctx["mandated_read_bytes"],
        "session_start_bytes": ctx["session_start_bytes"],
        "conditional_read_bytes": ctx["conditional_read_bytes"],
        "phantom_paths": phantoms["phantom_count"],
        "doc_count": len(docs),
        "doc_bytes": sum((root / d).stat().st_size for d in docs),
    }
    if args.gate:
        return report
    for name, (data, found) in {
        "duplication": lens_duplication(root, cfg, docs),
        "unbuilt": lens_unbuilt(root, cfg, files, docs),
        "state": lens_churn(root, cfg, hot, args.since),
        "gates": lens_gates(root, cfg, time_hooks=args.time_hooks),
        "usage": lens_usage(root, args.since, args.transcripts),
    }.items():
        report[name] = data
        report["findings"] += found
    report["metrics"].update(
        duplicate_pairs=len(report["duplication"]["duplicate_pairs"]),
        unbuilt_terms=len(report["unbuilt"].get("unbuilt_terms", {})),
        docs_only_commits=report["state"]["docs_only_commits"],
        commits=report["state"]["commits"],
        claude_hooks=len(report["gates"]["hooks"]),
        sync_check_stages=sum(
            len([s for s in v if not s.endswith("-async")]) for v in report["gates"]["check_matrix"].values()
        ),
        agents=len(list(root.glob(".claude/agents/*.md"))),
        skills=len(list(root.glob(".claude/skills/*/SKILL.md"))),
    )
    report["read_this_week"] = sorted(
        {
            *report["context"]["mandated_reads"],
            *(f["file"] for f in report["state"]["top_doc_churn"][:5]),
            *report["truth"]["phantom_paths"],
        }
    )[:15]
    return report


def render_md(report: dict, baseline: dict | None) -> str:
    """The report as markdown: metrics with deltas against the baseline, gate tables, and findings."""
    order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    lines = [
        f"# Harness audit at {report['head']} ({report['generated']}, window: since {report['since']})",
        "",
        "| Metric | Value | Change |",
        "|---|---|---|",
    ]
    for k, v in report["metrics"].items():
        old = (baseline or {}).get("metrics", {}).get(k)
        delta = "" if old is None or not isinstance(v, (int, float)) else f"{v - old:+,}"
        lines.append(f"| {k} | {v:,} | {delta} |" if isinstance(v, (int, float)) else f"| {k} | {v} | |")
    if baseline:
        before = {f["id"] for f in baseline.get("findings", [])}
        now = {f["id"] for f in report["findings"]}
        lines += ["", f"New findings: {len(now - before)}. Resolved since baseline: {len(before - now)}."]
    if report.get("gates", {}).get("timings"):
        lines += ["", "| Hook | Median seconds |", "|---|---|"]
        lines += [f"| {k} | {v['median_s']} |" for k, v in report["gates"]["timings"].items()]
    if report.get("gates", {}).get("check_matrix"):
        lines += ["", "| Check | Runs at |", "|---|---|"]
        lines += [f"| {k} | {', '.join(v)} |" for k, v in report["gates"]["check_matrix"].items()]
    lines += ["", "## Findings", ""]
    for f in sorted(report["findings"], key=lambda f: (order[f["severity"]], f["lens"])):
        lines.append(f"- **{f['severity']}** `{f['id']}` [{f['lens']}] {f['message']}")
        lines += [f"  - {e}" for e in f["evidence"][:6]]
    if report.get("read_this_week"):
        lines += ["", "## For the auditor: verify claims in these files", ""]
        lines += [f"- {f}" for f in report["read_this_week"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Run the audit from the command line; in gate mode, exit 1 when a finding is high."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path.cwd())
    ap.add_argument("--since", default=None)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--md", type=Path)
    ap.add_argument("--baseline", type=Path)
    ap.add_argument("--time-hooks", action="store_true")
    ap.add_argument("--transcripts", type=Path)
    ap.add_argument("--gate", action="store_true", help="cheap budget checks only; exit 1 on a high finding")
    ap.add_argument("--config", type=Path, help="a harness.toml outside the repository")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    cfg = load_config(root, args.config)
    args.since = args.since or cfg["since"]
    report = run(root, cfg, args)
    baseline = json.loads(args.baseline.read_text()) if args.baseline and args.baseline.exists() else None
    text = render_md(report, baseline)
    if args.json:
        args.json.write_text(json.dumps(report, indent=1, default=str))
    if args.md:
        args.md.write_text(text)
    if args.gate:
        high = [f for f in report["findings"] if f["severity"] == "high"]
        for f in high:
            print(f"harness: {f['message']}", file=sys.stderr)
            for e in f["evidence"][:6]:
                print(f"  {e}", file=sys.stderr)
        return 1 if high else 0
    if not args.md and not args.json:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
