"""The documents and agent context: CLAUDE.md, the always-on rule, CONSTRAINTS.md, the decision record."""

from __future__ import annotations

import json
from pathlib import Path

import commands
from intake import Project

TEMPLATES = Path(__file__).parent / "templates"
STARTERS = Path(__file__).parent / "starters"

SKILL_DENIES = (  # agent-skills pieces that write a second plan or ship outside serial-build's ledger
    "spec-driven-development",
    "planning-and-task-breakdown",
    "shipping-and-launch",
    "spec",
    "plan",
    "build",
    "ship",
)


def _fill(text: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


FLOORS = (
    "- Every module's path is a noun or a fixed package, and a role, from closed lists. A new noun, adapter\n"
    "  or surface is a change to the spec first, with a decision record: stop and ask.\n"
    "- No suppression for code you write: no noqa, no type-ignore, no per-file ignore, no hand edit to the\n"
    "  import contracts. When a check blocks something the conventions require, stop and say which."
)
RULE_PATHS = ("src/**", "tests/**", "tools/**", "migrations/**", "web/src/**", "project-spec.toml", "plants.toml")


def _values(p: Project) -> dict[str, str]:
    return {
        "project_name": p.name,
        "package": p.package,
        "slug": p.slug,
        "first_operation": p.first_operation,
        "web_plants": " (`plants.toml` and `web/plants.toml`)" if p.web else " (`plants.toml`)",
        "owner": p.owner_name or "the owner",
        "threat_model_readers": (
            ", and so do serial-build's red-breaker and red-fixer: the serial-build config names it as the threat "
            "model, so every red brief carries a copy"
            if p.addons["serial_build"]
            else ""
        ),
    }


def roots(p: Project) -> list[tuple[str, str]]:
    """Each top-level root: what it holds and what it never holds."""
    out = [
        (
            f"src/{p.package}/",
            "The backend: one package per noun, plus kernel, catalog, flows, adapters, surfaces "
            "and boot. Never scripts, fixtures or test tooling",
        ),
        ("tests/", "pytest, `tests/<noun>/test_<role>.py`. Never product code"),
        ("tools/", "The pinned toolkit, the check runner, git hooks. Never imported by the product"),
    ]
    if p.database != "none":
        out.append(("migrations/", "Numbered SQL; every table owned by one noun"))
    if p.web:
        out.append(("web/", "The front end; reaches the backend only through the generated client"))
    return out


def claude_md(p: Project) -> str:
    """CLAUDE.md when serial-build does not write it: what this is, where things live, the commands."""
    rows = "\n".join(f"| `{path}` | {holds} |" for path, holds in roots(p))
    return f"""# {p.name}

{p.summary}

The checks are listed in `CONSTRAINTS.md`; the architecture rules load from `.claude/rules/architecture.md`
when code is touched. Until the enforcement in `docs/tech/enforcement.md` is built, the plan for the session
is `docs/decisions/sources/{p.date}-bootstrap-prompt.md`.

## Floors

{FLOORS}

## Where things live

| Path | Holds |
|---|---|
{rows}
| `docs/tech/` | The conventions and how they are enforced |
| `docs/decisions/` | Dated, append-only decision records; `sources/` holds the briefs they acted on, verbatim |

## Commands

```
{commands.block(p)}
```
"""


def _kit_lines(p: Project) -> list[str]:
    out = []
    if "cli" in p.kits:
        out.append(
            "- **CLI**: the `better-cli` skill in `.claude/skills/` applies to every change to the CLI "
            "surface: data on stdout, diagnostics on stderr, `--json`, never a prompt, errors that name "
            "the next command."
        )
    if "mcp" in p.kits:
        out.append(
            "- **MCP**: the `mcp-surface` skill says how the MCP surface is built for a cold agent; "
            "audit it with `/mcp-legibility:legibility-audit --no-headless` after each change."
        )
    if "agents" in p.kits:
        out.append(
            "- **Agents**: the `agent-runs` skill: every model call is a traced span in its adapter, and "
            "each agent scenario is scored with agent-house against a committed baseline."
        )
    if p.addons["agent_skills"]:
        line = (
            "- **agent-skills**: technique skills (test-driven development, debugging, code review, security, "
            "API design) apply inside any slice."
        )
        if p.addons["serial_build"]:
            line += (
                " serial-build owns the lifecycle, so its spec, plan, build and ship skills are denied in "
                "`.claude/settings.json`; plan a gate with `/serial-build:gate`."
            )
        out.append(line)
    if p.addons["factory"]:
        out.append(
            "- **factory**: small, charter-permitted work arrives as GitHub issues and leaves as draft pull "
            "requests a person merges. With serial-build, anything the owner must run to accept goes "
            "through `/serial-build:intake` instead."
        )
    return out


def architecture_rule(p: Project) -> str:
    """The rule that loads when code is touched: the layout and pointers, never a second copy of a checked rule."""
    nouns = ", ".join(n.name for n in p.nouns)
    gate = ""
    if p.addons["serial_build"]:
        gate = (
            f"\n- With serial-build, a gate is one or more slices {p.owner_name} can run and judge; its QA "
            "lists the checks from `CONSTRAINTS.md` that prove it."
        )
    kits = _kit_lines(p)
    kit_text = "\n\n## Kits\n\n" + "\n".join(kits) if kits else ""
    paths = "\n".join(f'  - "{path}"' for path in RULE_PATHS)
    return f"""---
paths:
{paths}
---

# Architecture

- {p.name} is built from nouns ({nouns}), each a package under `src/{p.package}/` holding only the roles
  `ops`, `render`, `rules`, `store` and `model`. The fixed packages are `kernel`, `catalog`, `flows`,
  `adapters`, `surfaces` and `boot`. The rules and the reasons: `docs/tech/conventions.md`.
- New behaviour is an operation on a noun. A new noun, adapter or surface changes `project-spec.toml`
  first, then the contracts are re-rendered, then the code.
- `contracts.toml` is generated: `{commands.render_cmd(p, check=False)}`.
- A check is done when its plant is caught: `uv run python tools/toolkit/prove_checks.py plants.toml`.{gate}{kit_text}
"""


def constraints(p: Project) -> str:
    """CONSTRAINTS.md: the quality bar with the command behind every row, in agent-skills' format."""
    rows = "\n".join(
        f"| {c.dimension} | {c.rule} | {c.command} | {c.runs_at} | {c.status} |" for c in commands.checks(p)
    )
    plants = "`plants.toml`" + (" and `web/plants.toml`" if p.web else "")
    return f"""# Constraints

The quality bar for {p.name}, set before the first line of product code. Every row names the command
that gives the verdict; a row marked "starter" works now and is proven by a plant in {plants}; a row
marked "to build" is built by the first Claude Code session, with its plant, and then marked built. How the
checks are owned and kept: `docs/tech/enforcement.md`.

Read this before writing code. Do not weaken it to make a change pass.

## Floor (always enforced)

- No new suppression: no `noqa`, `type: ignore`, `@ts-ignore`, `biome-ignore`, per-file ignore or
  contract edit for code you write. When a rule blocks something the conventions require, stop and say which.
- No unimplemented stubs: no `raise NotImplementedError`, no function whose body is `pass`, no empty `except`.
- No skipped or deleted tests without a reason in the commit message; a skipped database test is a failure.
- No secrets in source.
- This file, `ruff.toml`, `project-spec.toml`, `contracts.toml` and the web configs are not weakened to make a
  change pass.

## Enforced with commands

| Dimension | Rule | Checked by | Runs at | Status |
|---|---|---|---|---|
{rows}

Every row names the command that produces the verdict. A dimension with no command is an aspiration, not a
constraint.

## Measured, not yet enforced

None yet. When a number is worth holding (coverage of changed lines, bundle size, an agent run's cost),
measure it, write today's value here, and hold the direction.

## Exceptions

None. Ledgers start empty and may only shrink against `main`. An exception exists only with
`Debt-Raised: <reason>` in its commit message, and is listed here with its owner and expiry.

| ID | Rule | Path | Reason | Owner | Expires |
|---|---|---|---|---|---|
"""


def decision(p: Project, briefs: list[str]) -> str:
    """The first decision record: the architecture as confirmed at intake."""
    nouns = "\n".join(
        f"- `{n.name}`: {n.purpose} Operations: {', '.join(n.operations)}."
        + (f" Owns {', '.join(n.owns)}." if n.owns else "")
        + (f" Depends on {', '.join(n.depends_on)}." if n.depends_on else "")
        for n in p.nouns
    )
    adapters = ", ".join(f"`{a.name}` over {a.wraps}" for a in p.adapters) or "none yet"
    flows = ", ".join(f.name for f in p.flows) or "none yet"  # plain: the audit reads code spans as code names
    rejected = "\n".join(r if r.startswith("- ") else f"- {r}" for r in p.rejected) or (
        "- Nothing else was offered at intake; the next record that changes the nouns names its alternatives."
    )
    sources = "".join(f"\n- `docs/decisions/sources/{b}`" for b in briefs)
    reopens = p.reopens or "A noun's operations stop sharing one subject, or every change touches two nouns at once."
    return f"""# Architecture

Date: {p.date}

## Decided

**{p.name} is built from {len(p.nouns)} noun{"s" if len(p.nouns) != 1 else ""}.**

{nouns}

**Ways in: {", ".join(p.surfaces)}.** Every one is a projection of the operation catalog.
Adapters: {adapters}. Flows: {flows}. Database: {p.database}.

**The first slice is `{p.first_operation}`**, built end to end through every surface it declares.

**Add-ons:** serial-build {_on(p.addons["serial_build"])}, agent-skills {_on(p.addons["agent_skills"])},
factory {_on(p.addons["factory"])}.

Sources, kept verbatim:
- `docs/decisions/sources/{p.date}-intake.json`, the confirmed intake the scaffold was generated from
- `docs/decisions/sources/{p.date}-bootstrap-prompt.md`, the plan for the first session{sources}

## Rejected

{rejected}

## Reopens if

{reopens}
"""


def _on(flag: bool) -> str:
    return "on" if flag else "off"


def settings(p: Project) -> str:
    """`.claude/settings.json`: the plugins this project uses, declared so every clone gets them."""
    markets, enabled = {}, {}
    if p.addons["serial_build"]:
        markets["serial-build-harness"] = {
            "source": {"source": "github", "repo": "DMG-Venture-Studio/serial-build-harness"}
        }
        enabled["serial-build@serial-build-harness"] = True
    if p.addons["agent_skills"]:
        markets["addy-agent-skills"] = {"source": {"source": "github", "repo": "addyosmani/agent-skills"}}
        enabled["agent-skills@addy-agent-skills"] = True
    if "mcp" in p.kits:
        markets["mcp-legibility"] = {"source": {"source": "github", "repo": "DMG-Venture-Studio/mcp-legibility"}}
        enabled["mcp-legibility@mcp-legibility"] = True
    out: dict[str, object] = {}
    if markets:
        out |= {"extraKnownMarketplaces": markets, "enabledPlugins": enabled}
    if p.addons["agent_skills"] and p.addons["serial_build"]:
        deny = [form.format(f"agent-skills:{name}") for name in SKILL_DENIES for form in ("Skill({})", "Skill({} *)")]
        # A typed /agent-skills:plan still expands its command text; these stop the second plan it would write.
        deny += ["Edit(/tasks/**)", "Edit(/SPEC.md)"]
        out["permissions"] = {"deny": deny}
    return json.dumps(out, indent=2) + "\n"


def gitignore(p: Project) -> str:
    lines = [
        ".venv/",
        "__pycache__/",
        "*.pyc",
        ".pytest_cache/",
        ".ruff_cache/",
        ".import_linter_cache/",
        ".env",
        ".DS_Store",
        ".claude/settings.local.json",
    ]
    if p.web:
        lines += ["node_modules/", "web/dist/"]
    return "\n".join(lines) + "\n"


def ruff_toml(p: Project) -> str:
    text = (STARTERS / "ruff.toml").read_text()
    text = text.replace("banned-module-level-imports = []", f"banned-module-level-imports = {json.dumps(list(p.lazy))}")
    if "cli" in p.kits:  # ruff formats Python blocks in Markdown; a vendored skill is not ours to reformat
        text = text.replace(
            'src = ["src", "tests"]\n', 'src = ["src", "tests"]\nextend-exclude = [".claude/skills/better-cli"]\n'
        )
    return text


def files(p: Project, briefs: list[str]) -> dict[str, str]:
    """Every document and agent-context file, by path."""
    values = _values(p)
    out = {
        "CONSTRAINTS.md": constraints(p),
        ".claude/rules/architecture.md": architecture_rule(p),
        "docs/tech/conventions.md": _fill((TEMPLATES / "docs" / "conventions.md").read_text(), values),
        "docs/tech/enforcement.md": _fill((TEMPLATES / "docs" / "enforcement.md").read_text(), values),
        f"docs/decisions/{p.date}-architecture.md": decision(p, briefs),
        ".gitignore": gitignore(p),
        "ruff.toml": ruff_toml(p),
    }
    if not p.addons["serial_build"]:
        out["CLAUDE.md"] = claude_md(p)
    if settings(p).strip() != "{}":
        out[".claude/settings.json"] = settings(p)
    return out
