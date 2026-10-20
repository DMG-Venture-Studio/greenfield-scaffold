"""The prompt for the first Claude Code session, rendered for this project's add-ons and repository."""

from __future__ import annotations

import commands
from intake import Project

FACTORY_REF = "8af1165"


def _repo(p: Project) -> str:
    org, name = p.repo.get("org", ""), p.repo.get("name", p.slug)
    remote = p.repo.get("remote", "none") if org else "none"
    lines = [
        "- If `git status` says this is not a repository, or `git log` is empty: "
        f'`git init -b main && git add -A && git commit -m "Scaffold {p.name}"`.',
    ]
    if remote == "created" and org:
        lines.append(
            f"- The remote exists: `https://github.com/{org}/{name}`. If `git remote -v` does not list it, "
            f"`git remote add origin https://github.com/{org}/{name}.git`. Then `git push -u origin main`."
        )
    elif remote == "to-create":
        lines.append(
            f"- Create the remote and push: `gh repo create {org}/{name} --{p.repo['visibility']} --source . "
            "--remote origin --push`. If `gh` is not signed in, stop and ask for `gh auth login`."
        )
    else:
        lines.append("- No remote was asked for. Do not create one.")
    return "\n".join(lines)


def _plugins(p: Project) -> str:
    names = []
    if p.addons["serial_build"]:
        names.append("`serial-build@serial-build-harness`")
    if p.addons["agent_skills"]:
        names.append("`agent-skills@addy-agent-skills`")
    if "mcp" in p.kits:
        names.append("`mcp-legibility@mcp-legibility`")
    if not names:
        return ""
    text = (
        f"\n## 1. Plugins\n\n`.claude/settings.json` declares {', '.join(names)}. Trust the folder when asked, "
        "accept the install prompts (or `/plugin install <name>` each), then `/reload-plugins`, and confirm in "
        "`/plugin` that each is enabled.\n"
    )
    if p.addons["agent_skills"] and p.addons["serial_build"]:
        text += (
            "\nThe settings deny agent-skills' `spec-driven-development`, `planning-and-task-breakdown` and "
            "`shipping-and-launch` skills and its `spec`, `plan`, `build` and `ship` commands, and deny writes to "
            "`tasks/**` and `SPEC.md`, because those write a second plan beside serial-build's one active plan. A "
            "typed `/agent-skills:plan` still expands its own text, but the planning skill it calls is blocked and "
            "the write to `tasks/plan.md` is refused. Prove both: run `/agent-skills:plan add a refund`, and show "
            "`Skill execution blocked by permission rules` and the refused write. If either is not refused, say so "
            "and stop; do not work around it.\n"
        )
    return text


def _harness(p: Project) -> str:
    if not p.addons["serial_build"]:
        return ""
    return (
        "\n## 2. The harness\n\nRun `/serial-build:scope`. It finds `.claude/serial-build.json` and the saved "
        f"answers in `docs/decisions/sources/scoping-answers-{p.date}.json`, so it does not interview again: "
        "choose to fill the missing files. It writes `CLAUDE.md`, the design, the roadmap with the first gate "
        f"(`{p.harness['first_gate_slug']}`), the glossary, its rules and the inbox. Its config and canon checks "
        "must both pass. Commit.\n"
    )


def _hooks(p: Project) -> str:
    if p.addons["serial_build"]:
        return (
            "3. **Claude Code hooks.** serial-build's hooks already run ruff on the edited file after every edit, "
            "and the contracts, types, deptry and the tests when a turn ends, from `.claude/serial-build.json`: "
            "that end-of-turn hook is those checks' one local stage, so the pre-commit hook does not repeat them. "
            "Add only what serial-build lacks, in `.claude/settings.json` (merged, never replaced): the new-module "
            "guard on Write, the commit and push refusals of `--no-verify`, `-n` and hooks-path overrides, and the "
            "session-start warning when git hooks are off. Each hook gets a plant; none is pinned by digest."
        )
    return (
        "3. **Claude Code hooks** in `.claude/settings.json` (merged, never replaced): the new-module guard on Write, "
        "ruff and its formatter on the edited file only after Edit and Write (under a second; whole-project checks "
        "belong to the commit), the commit and push refusals of `--no-verify`, `-n` and hooks-path overrides, and "
        "the session-start warning. Each hook gets a plant; none is pinned by digest."
    )


def _kits(p: Project) -> str:
    out = []
    if "mcp" in p.kits:
        out.append(
            "   - **MCP legibility.** Turn its row in `CONSTRAINTS.md` into a check: mcp-legibility's static "
            "probe on this repository reports an `instructions=` block with an entry point. Read the "
            "`mcp-surface` skill first."
        )
    if "agents" in p.kits:
        out.append(
            "   - **Agent runs.** Turn its row into a check once the first agent scenario has a recorded "
            "trace and an accepted baseline. Read the `agent-runs` skill first."
        )
    if "credentials" in p.kits:
        out.append(
            "   - **Credential age.** Read the `credentials` skill first. Build its row as a weekly CI job running "
            "`credentials.py audit`, signed in to Infisical through GitHub's OIDC (a machine identity with OIDC "
            "auth bound to this repository, read-only on the project), so no Infisical token is stored anywhere. "
            "Never ask for, paste or read a key's value in this session: minting is the owner's, with "
            "`credentials.py provision`."
        )
    return ("\n" + "\n".join(out)) if out else ""


def _skeleton(p: Project) -> str:
    noun = p.first_noun.name
    web = (
        f", and, with the front end, a page in `web/src/nouns/{noun}/` that calls it through the generated client"
        if p.web and p.first_noun.screens
        else ""
    )
    if p.addons["serial_build"]:
        return (
            f"7. **The first gate.** The walking skeleton is the first gate, `{p.harness['first_gate_slug']}`: "
            f"`{p.first_operation}` as one slice through every role it needs and every way in it declares{web}. "
            "Do not build it as part of this session's enforcement work: plan it with `/serial-build:gate`, which "
            f"runs the adversarial review, and {p.owner_name} accepts it by running its demo."
        )
    return (
        f"7. **Walking skeleton.** One operation, `{p.first_operation}`, as a full slice: `ops` and the roles it "
        f"needs, a migration owned by `{noun}` if it owns a table, reachable from every declared way in through "
        f"the catalog, with its parity test{web}."
    )


def _factory(p: Project) -> str:
    if not p.addons["factory"]:
        return ""
    pkg, owner = p.package, p.owner_name or "the owner"
    has_settings = p.addons["serial_build"] or p.addons["agent_skills"] or "mcp" in p.kits
    skip_text = (
        "on this scaffold it skips exactly two, `CLAUDE.md` and `.claude/settings.json`"
        if has_settings
        else "on this scaffold it skips only `CLAUDE.md`, and creates `.claude/settings.json`"
    )
    merge_settings = (
        "; `.claude/settings.json` gains its `permissions` and the block-merge `PreToolUse` hook, merged into what "
        "is there"
        if has_settings
        else ""
    )
    needs_spec = (
        f"      - Anything {owner} must run to accept: route it to `/serial-build:intake`, which files it as a gate"
        if p.addons["serial_build"]
        else "      - Anything adding a user-visible feature"
    )
    return f"""
8. **factory, last.** Once merged, its settings deny edits to `.claude/settings.json`, `AGENTS.md` and its gate
   script, which would block the steps above. Its installer never overwrites a file; {skip_text}.
   - `git clone https://github.com/addyosmani/factory /tmp/factory && git -C /tmp/factory checkout {FACTORY_REF}`,
     then `/tmp/factory/install.sh --dry-run .` and `/tmp/factory/install.sh .`.
   - Merge what the installer skipped because the file already exists: `CLAUDE.md` gains the "Factory rules"
     section of `/tmp/factory/template/CLAUDE.md`{merge_settings}.
   - In `.claude/scripts/gates.sh`, the DETECT block's python branch runs whatever `ruff` and `mypy` are on
     the PATH, not the pinned ruff and pyrefly, and never sees `web/`. Make it run this project's commands: types
     `uv run pyrefly check`; lint `uv run ruff check . && uv run ruff format --check .`; test `uv run pytest -q`;
     architecture `{commands.render_cmd(p, check=True)} && PYTHONPATH=src uv run lint-imports --config contracts.toml`;
     audit `uv run --with pip-audit pip-audit`. Show `./.claude/scripts/gates.sh deep` ending `status=GREEN`.
   - Pre-fill `docs/factory/CHARTER.md` and leave `CHARTER_STATUS: incomplete`; {owner} reviews and sets it:
     - `TIER: greenfield`
     - `LOAD_BEARING`: `project-spec.toml`, `contracts.toml`, `ruff.toml`, `CONSTRAINTS.md`, `tools/**`,
       `src/{pkg}/kernel/**`, `src/{pkg}/catalog/**`, `migrations/**`, `.claude/**`, `.github/workflows/**`
     - `AUTOMATABLE`: dependency bumps that pass full gates; lint, format and type fixes; docs; tests for
       untested functions; single-file bug fixes with a failing test
     - `NEEDS_SPEC`:
{needs_spec}
      - Any new operation, noun, adapter or surface (a spec change)
   - A `factory:ready-to-spec` issue is taken by {"`/serial-build:intake`" if p.addons["serial_build"] else "the factory-spec skill"}, so one ledger holds product work.
   - Labels: `bash .factory/scripts/bootstrap-github.sh`. Routines are set up in the claude.ai UI from
     `/tmp/factory/ROUTINES.md`. Cloud runs load no plugins, so the git hooks and CI hold the checks there.
"""


def render(p: Project, toolkit_version: str, briefs: list[str]) -> str:
    """The whole bootstrap prompt."""
    nouns = ", ".join(n.name for n in p.nouns)
    adapters = ", ".join(a.name for a in p.adapters) or "none yet"
    reads = [
        "`docs/tech/conventions.md`: the architecture.",
        "`docs/tech/enforcement.md`: how checks are owned and proven, and the acceptance list below.",
        "`CONSTRAINTS.md`: every check, its command, and which ones you build.",
        f"`project-spec.toml`: the nouns ({nouns}), ways in ({', '.join(p.surfaces)}), adapters ({adapters}).",
        f"`tools/toolkit/README.md`: the shared toolkit, version {toolkit_version}. Use it as it is.",
    ]
    reads += [f"`docs/decisions/sources/{b}`: a brief this project started from." for b in briefs]
    read_list = "\n".join(f"{i}. {r}" for i, r in enumerate(reads, 1))
    finish = (
        "hand the first gate to serial-build"
        if p.addons["serial_build"]
        else ("finish with one slice that runs end to end through every way in")
    )
    return f"""# Bootstrap prompt: the first Claude Code session

From the project folder in cmux: `claude "$(cat docs/decisions/sources/{p.date}-bootstrap-prompt.md)"`,
or paste everything below the line into a new Claude Code session opened on this folder.

---

You are setting up the enforcement for a new project, **{p.name}**, before any feature work. The scaffolder
wrote the skeleton, the spec, the starter checks and a plant for each. Your job is to make the conventions
impossible to drift from, prove every check works, and {finish}.

## 0. The repository and the scaffold's own checks

{_repo(p)}
- Run every command in this block. Each passes on the scaffold, and every `prove_checks.py` line says `caught`:

```
{commands.block(p)}
```

If anything fails here, stop and report it with the output. A scaffold that fails its own checks is a
scaffolder bug, not something to fix in this project.
{_plugins(p)}{_harness(p)}
## Read before building

{read_list}

## Rules for this session

- Do not loosen a starter. No rule removed from `ruff.toml`, no limit raised, no contract edited by hand, no
  `noqa`, `type: ignore` or per-file ignore added for code you write. If a starter rule blocks something the
  conventions require, stop and say which rule and why; do not work around it.
- Do not rewrite toolkit pieces. If one does not fit, say what is missing; do not fork it. A piece the toolkit
  does not have yet is built under `tools/` in the smallest form that passes its plants.
- Generated files are generated: `contracts.toml`, the agent rules under `.claude/rules/`, `openapi.json`, the
  MCP tool list, the CLI help snapshot and `web/src/generated/`. Each gets a `--check` drift check.
- Every check you add gets at least one plant in `plants.toml`{" (or `web/plants.toml`)" if p.web else ""} before you rely on
  it. Run `prove_checks.py` after each check; a check whose plant is MISSED is not done.
- Commit after each step with a message that says what the check refuses and names the plant that proved it.

## Build, in this order

1. **Check runner.** `make check` (backed by `tools/check.py`) runs every row of `CONSTRAINTS.md` that works,
   one summary line per check, under 15 seconds on this empty project.
2. **Git hooks.** `tools/git_hooks/` with pre-commit (the checks whose local stage in `CONSTRAINTS.md` is the
   commit, and `harness_audit.py --gate`), commit-msg (debt ratchet), pre-push (everything plus the review
   check) and pre-merge-commit. `make setup` sets `core.hooksPath`. Each hook gets a plant. A check runs at
   one local stage, then at push and in CI, never at every local stage.
{_hooks(p)}
4. **Project checks.** Each "to build" row of `CONSTRAINTS.md`: one home, ways in, surface parity, the debt
   ratchet{", table ownership" if p.database != "none" else ""}{", knip and client drift" if p.web else ""}. Each becomes a command with a plant, and its row says "built".{_kits(p)}
5. **Agent context.** Path-scoped rules under `.claude/rules/`, one per noun and tier, rendered from the spec
   and the module docstrings, with their drift check. The reviewer agents, each answering one question and
   flagging rather than blocking: {"authority and sprawl (serial-build already ships an adversarial reviewer and a red-breaker)" if p.addons["serial_build"] else "adversarial, authority and sprawl"}, wired into the pre-push review check.
6. **CI** running `make check` and the tests on every push and pull request, plus a weekly job that runs the
   plants and posts the ledger counts. `.github/workflows/harness-audit.yml` is already here: the weekly
   harness audit, its auditor when `vars.HARNESS_MODEL` is `true`, and issues when `vars.HARNESS_ISSUES` is.
   Before finishing, run `uv run python tools/toolkit/harness_audit.py --time-hooks` and fix every high or
   medium finding your own work caused.
{_skeleton(p)}{_factory(p)}
## Finish with one message containing

- the output of `make check`;
- the output of every `prove_checks.py` run, every line `caught`;
- the refused `git commit --no-verify` attempt, shown;
- the list of ledgers, each empty;
- `CONSTRAINTS.md` with no row left "to build", or the reason each remaining one is not;
- anything in the conventions or the enforcement document you could not hold mechanically, with the reason,
  so it can go to a reviewer agent or back to the scaffolder.
"""
