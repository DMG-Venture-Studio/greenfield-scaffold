"""Plants for harness_audit.py: a clean repository yields none of these findings, and each plant yields its own.
Run: python -m pytest -q test_harness_audit.py   (or: python test_harness_audit.py)"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLKIT = Path(__file__).resolve().parents[2] / "plugins" / "greenfield" / "engine" / "toolkit"
sys.path.insert(0, str(TOOLKIT))
import harness_audit  # noqa: E402

CLEAN = {
    "AGENTS.md": "# Rules\n\nRun `make check` before pushing. Read [the status page](docs/status.md) before changing anything.\n",
    "docs/status.md": "# Status\n\nThe invoice noun sends one invoice.\n",
    "src/app/invoice.py": '"""Invoices."""\n\n\ndef invoice_send():\n    return "sent"\n',
    "tools/git_hooks/pre-commit": "#!/bin/sh\nmake check\n",  # made executable in make_repo
    ".github/workflows/check.yml": "jobs:\n  check:\n    steps:\n      - run: make check\n      - run: pytest -q\n",
    ".claude/settings.json": json.dumps(
        {
            "hooks": {
                "PostToolUse": [
                    {"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "ruff check --quiet . || true"}]}
                ]
            }
        }
    ),
}
PARAGRAPH = (
    "Every operation declares its grant once and the catalog checks it before the operation runs, so a surface "
    "never decides who may call what and a new surface inherits the same authority without any extra code at all."
)


def make_repo(files: dict, extra_commits: int = 0, docs_only: bool = False) -> Path:
    root = Path(tempfile.mkdtemp(prefix="plant-")) / "repo"
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        if "git_hooks/" in rel or rel.endswith(".sh"):
            p.chmod(0o755)
    run = lambda *a: subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True)  # noqa: E731
    run("init", "-q")
    run("config", "user.email", "plant@example.com")
    run("config", "user.name", "plant")
    run("config", "core.hooksPath", "tools/git_hooks")
    run("add", "-A")
    run("commit", "-qm", "base", "--no-verify")
    for i in range(extra_commits):
        target = root / ("docs/status.md" if docs_only else f"src/app/m{i}.py")
        target.write_text(target.read_text() + f"\n# {i}\n" if target.exists() else f"X = {i}\n")
        run("add", "-A")
        run("commit", "-qm", f"change {i}", "--no-verify")
    return root


def audit(root: Path, *flags: str) -> tuple[int, dict]:
    out = root.parent / "report.json"
    code = harness_audit.main(["--root", str(root), "--json", str(out), "--since", "1 year ago", *flags])
    return code, json.loads(out.read_text())


def keys(report: dict) -> set[str]:
    return {f"{f['lens']}:{f['key']}" for f in report["findings"]}


PLANTS = {
    "mandated reading over budget": (
        {"AGENTS.md": CLEAN["AGENTS.md"] + "\nRead [the big doc](docs/big.md) first.\n", "docs/big.md": "word " * 6000},
        "context:mandated_reads",
    ),
    "always-loaded over budget": ({"AGENTS.md": CLEAN["AGENTS.md"] + "rule.\n" * 2200}, "context:always_loaded"),
    "phantom path in AGENTS.md": (
        {"AGENTS.md": CLEAN["AGENTS.md"] + "The runner is `src/app/ghost.py`.\n"},
        "truth:phantom:AGENTS.md",
    ),
    "duplicated paragraph": (
        {"docs/a.md": PARAGRAPH, "docs/b.md": "Intro.\n\n" + PARAGRAPH},
        "duplication:dup:docs/a.md|docs/b.md",
    ),
    "unbuilt system named in docs": ({"docs/plan.md": "Orders sync to Medusa nightly. " * 6}, "unbuilt:term:Medusa"),
    "unbuilt identifier in docs": ({"docs/plan.md": "Call `outbox.flush` after each write.\n"}, "unbuilt:identifiers"),
    "whole-project check on every edit": (
        {
            ".claude/settings.json": json.dumps(
                {
                    "hooks": {
                        "PostToolUse": [
                            {
                                "matcher": "Edit|Write",
                                "hooks": [{"type": "command", "command": "python tools/check.py"}],
                            }
                        ]
                    }
                }
            ),
            "tools/check.py": "print('ok')\n",
        },
        "gates:edit_whole_project:project check",
    ),
    "gate pins its own hook by digest": (
        {
            ".claude/settings.json": json.dumps(
                {
                    "hooks": {
                        "PostToolUse": [
                            {
                                "matcher": "Edit",
                                "hooks": [{"type": "command", "command": "sh .claude/hooks/post_edit.sh"}],
                            }
                        ]
                    }
                }
            ),
            ".claude/hooks/post_edit.sh": "#!/bin/sh\nexit 0\n",
            "tools/pins.py": 'HOOK_DIGESTS = {"post_edit.sh": "0123456789abcdef"}\n',
        },
        "gates:self_pinning",
    ),
    "nested instruction file": (
        {"skills/x/AGENTS.md": "Follow these principles in this project.\n"},
        "context:nested:skills/x/AGENTS.md",
    ),
    "agent never used": (
        {".claude/agents/foo.md": "---\nname: foo\ndescription: Reviews foo.\n---\nBody.\n"},
        "usage:unused:foo",
    ),
}


def test_clean_repository_has_none_of_the_planted_findings():
    _, report = audit(make_repo(CLEAN))
    planted = {k for _, k in PLANTS.values()} | {"state:docs_only_share", "gates:slow:edit sleep.sh (py)"}
    assert not (keys(report) & planted), keys(report) & planted


def test_each_plant_is_caught():
    missed = []
    for name, (overlay, key) in PLANTS.items():
        _, report = audit(make_repo({**CLEAN, **overlay}))
        if key not in keys(report):
            missed.append(f"{name}: expected {key}, got {sorted(keys(report))}")
    assert not missed, "\n".join(missed)


def test_the_commit_that_adds_an_agent_is_not_a_use_of_it():
    root = make_repo(CLEAN)
    agent = root / ".claude/agents/bar.md"
    agent.parent.mkdir(parents=True, exist_ok=True)
    agent.write_text("---\nname: bar\ndescription: Reviews bar.\n---\n")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "Add the bar reviewer", "--no-verify"], check=True)
    _, report = audit(root)
    assert "usage:unused:bar" in keys(report), report["usage"]


def test_docs_only_commits_are_counted():
    _, report = audit(make_repo(CLEAN, extra_commits=6, docs_only=True))
    assert "state:docs_only_share" in keys(report)


def test_gate_mode_exits_nonzero_on_a_breach_and_zero_when_clean():
    clean_code, _ = audit(make_repo(CLEAN), "--gate")
    overlay, _ = PLANTS["mandated reading over budget"]
    breach_code, _ = audit(make_repo({**CLEAN, **overlay}), "--gate")
    assert (clean_code, breach_code) == (0, 1)


def test_slow_edit_hook_is_timed_in_a_worktree_and_flagged():
    overlay = {
        ".claude/settings.json": json.dumps(
            {
                "hooks": {
                    "PostToolUse": [
                        {
                            "matcher": "Edit|Write",
                            "hooks": [
                                {"type": "command", "command": 'sh "$CLAUDE_PROJECT_DIR"/.claude/hooks/sleep.sh'}
                            ],
                        }
                    ]
                }
            }
        ),
        ".claude/hooks/sleep.sh": "#!/bin/sh\nsleep 1.2\n",
        "harness.toml": '[harness.samples]\npy = "src/app/invoice.py"\n',
    }
    root = make_repo({**CLEAN, **overlay})
    _, report = audit(root, "--time-hooks")
    assert any(k.startswith("gates:slow:edit sleep.sh") for k in keys(report)), sorted(keys(report))
    listed = subprocess.run(["git", "-C", str(root), "worktree", "list"], capture_output=True, text=True).stdout
    assert len(listed.strip().splitlines()) == 1, f"the timing worktree was left behind:\n{listed}"


# Precision plants: each of these must NOT produce the finding a naive scan would.
def test_conditional_reads_and_navigation_tables_are_not_session_start_reading():
    big = "word " * 6000
    overlay = {
        "AGENTS.md": CLEAN["AGENTS.md"] + "\nRead [the SDK notes](docs/sdk.md) before touching the SDK modules.\n"
        "\n| Document | Holds |\n|---|---|\n| [Design](docs/design.md) | where to read the design |\n",
        "docs/sdk.md": big,
        "docs/design.md": big,
    }
    _, report = audit(make_repo({**CLEAN, **overlay}))
    ctx = report["context"]
    assert ctx["mandated_read_bytes"] < 1000, ctx["mandated_reads"]
    assert ctx["conditional_read_bytes"] >= 30000, ctx["mandated_reads"]
    assert "docs/design.md" not in ctx["mandated_reads"]


def test_a_sentence_mixing_unconditional_and_conditional_reads_is_split_per_reference():
    overlay = {
        "AGENTS.md": "Status is on the [status page](docs/status.md). Before changing anything, read the status page, "
        "[decisions](docs/decisions.md) and the design document for the area you touch.\n\n"
        "Read [the SDK notes](docs/sdk.md) before touching any of them.\n\n"
        "Read [the handoff](docs/handoff.md); look a decision up in [the record](docs/record.md) when you touch it.\n",
        "docs/decisions.md": "x",
        "docs/handoff.md": "x",
        "docs/record.md": "x",
        "docs/sdk.md": "x",
    }
    _, report = audit(make_repo({**CLEAN, **overlay}))
    reads = {k: v["conditional"] for k, v in report["context"]["mandated_reads"].items()}
    expected = {"docs/status.md": False, "docs/decisions.md": False, "docs/sdk.md": True, "docs/handoff.md": False}
    assert reads == expected, reads


def test_commented_commands_and_package_relative_paths_are_not_findings():
    overlay = {
        ".claude/settings.json": json.dumps(
            {
                "hooks": {
                    "PostToolUse": [
                        {"matcher": "Edit", "hooks": [{"type": "command", "command": "sh .claude/hooks/lint.sh"}]}
                    ]
                }
            }
        ),
        ".claude/hooks/lint.sh": "#!/bin/sh\n# The project check (tools/check.py) runs at commit, not here.\nexit 0\n",
        "docs/status.md": CLEAN["docs/status.md"] + "The send lives in `app/invoice.py`.\n",
    }
    _, report = audit(make_repo({**CLEAN, **overlay}))
    assert "edit" not in report["gates"]["check_matrix"].get("project check", []), report["gates"]["check_matrix"]
    assert "docs/status.md" not in report["truth"]["phantom_paths"], report["truth"]["phantom_paths"]


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print(f"caught  {name}")
            except AssertionError as e:
                failures += 1
                print(f"MISSED  {name}\n{e}")
    sys.exit(1 if failures else 0)
