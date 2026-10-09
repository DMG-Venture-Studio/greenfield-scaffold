# Enforcement: what keeps the conventions true after day one

The checks themselves, with their commands and when they run, are listed in `CONSTRAINTS.md`. This document
says how they are owned, proven and kept, and what the first Claude Code session must leave behind.

## Principles

1. **A rule that matters is a check.** Prose explains the rule; the check holds it. Instructions in
   `CLAUDE.md` and `.claude/rules/` are context, not enforcement.
2. **No check is trusted until it has failed.** Every check has at least one planted violation in a plants
   file, and `prove_checks.py` shows the check refusing it and the tree coming back clean. The plants re-run
   on a schedule, so a check that quietly stops working is caught.
3. **Generated, never hand-kept.** The import contracts, the path-scoped agent rules, the OpenAPI document,
   the MCP tool list, the CLI help and the web client are rendered from the spec or the catalog, and each
   has a `--check` drift check.
4. **No architecture exemptions.** The contracts are rendered from `project-spec.toml`; the only way to
   allow an import is to change the spec, which is a reviewed decision. Lint exemptions live in one ledger
   per tool, start empty, and may only shrink against `main`.
5. **Agents cannot switch checks off.** `--no-verify` and hooks-path overrides are refused, every hook has
   a plant that proves it still refuses, and any change to a check's configuration needs the adversarial
   reviewer's report. Hooks are not pinned by digest: a digest inside a check makes every hook edit a check
   change, while a plant proves the hook works without freezing its file.
6. **One local stage, then push and CI.** Each check runs with the same command at one local stage (the
   edit hook, the end of a turn, or the commit hook), again at push, and in CI, which branch protection
   requires. A check repeated at every local stage costs every session time and catches nothing new; the
   harness audit flags it. Plugins do not load in cloud sessions, so a scheduled cloud run is held by the
   git hooks and CI, never by a plugin's hooks alone.
7. **The agent's context is held to a budget.** What loads into every session, what instruction files make
   it read, and what the docs claim that the tree does not hold are measured by
   `tools/toolkit/harness_audit.py`, against the numbers in `harness.toml`, which only go down. Its `--gate`
   mode refuses a commit that breaks a budget or names a missing path in an always-loaded file.

## Who owns what

| Owner | Delivers | Why there |
|---|---|---|
| Scaffolder (deterministic) | `project-spec.toml`; the directory skeleton; the starters (`ruff.toml`, rendered contracts, web configs); the plants for every starter check; these documents; the first decision record; the bootstrap prompt | Same on every project; no judgment needed once the spec is confirmed. |
| Shared toolkit (versioned, pinned in `tools/toolkit/`) | `render_import_contracts.py`, `prove_checks.py`, `harness_audit.py`, `harness_issues.py`; later the debt ratchet, the one-home check, the ways-in reader, the agent-rules renderer and the new-module guard | Project-independent and easy to get subtly wrong. Built once, tested, versioned, copied in at a pinned version, never rewritten per project. |
| Claude Code (per project) | The check runner, git and Claude Code hooks wired to it, CI, catalog-to-surface projections with parity tests, the table-ownership check, the reviewer agents, and plants for every check it adds | Depends on this project's spec, surfaces and stack. |

Do not write the generic check machinery from scratch in each project. In the project these conventions came
from, the bespoke check grew past 1,800 lines, and an adversarial review still found real gaps; afterwards,
five planted entry-point evasions still passed it. While the starters were written, a plant harness that
lost its restore step corrupted the tree it was proving. Check code needs its own tests, and a shared,
versioned toolkit is where those tests live. A toolkit piece that does not exist yet is built here in the
smallest form that passes its plants, and reported back to the scaffolder so it can join the toolkit.

## Agents and process

| Piece | Holds |
|---|---|
| Git hooks in `tools/git_hooks/`, `core.hooksPath` set by `make setup` | pre-commit and pre-merge-commit run the checks whose local stage is the commit, and the harness audit's `--gate`; commit-msg runs the debt ratchet; pre-push runs everything plus the review check. |
| Claude Code hooks | **PreToolUse on Write**: a new file whose path is not on the closed lists is refused with the layout shown. **PostToolUse on Edit and Write**: ruff on the touched file only, under a second, refusing with the output. **PreToolUse on Bash**: commit and push refuse `--no-verify`, `-n` in any short-flag run, and hooks-path overrides. **SessionStart**: warns when git hooks are off or the test database is down. Each hook has a plant. |
| `CLAUDE.md` and `.claude/rules/` | Short: the invariants, the commands, pointers to these documents. Never a second copy of a rule a check holds. |
| Path-scoped rules | One `.claude/rules/` file per noun and tier, rendered from the spec and the module docstrings (what each module is for, what it may import), with a drift check; the files are on the pre-edit refusal list. |
| Reviewer agents | One question each, flag and route, never block alone: **adversarial** (does the code do what the commit claims), **authority** (grants, spend, secrets), **sprawl** (does this give an idea a second home). The pre-push review check requires their reports for the paths they cover. |
| Decision records | One per new noun, adapter or surface, or rule change, naming the rejected alternative (format in `docs/tech/conventions.md`). |
| Harness audit | `tools/toolkit/harness_audit.py` measures context weight, phantom paths, duplicated text, names with no code, state kept in prose, check cost and repetition, and agent and skill use. The `harness-auditor` agent judges what it cannot measure, weekly, and a finding raised a third time must come with a check. |
| CI | The same commands; required by branch protection; the plants and the harness audit weekly. |

## Acceptance for the first session

The enforcement work is finished when all of these hold and the session's last message shows them:

- `make check` runs every check in `CONSTRAINTS.md` that applies, in under 15 seconds on the empty project.
- `uv run python tools/toolkit/harness_audit.py` reports no high or medium finding the session's own work
  caused, and `--time-hooks` shows the edit hook under a second.
- `prove_checks.py` passes on every plants file{{web_plants}}: every check has at least one plant, every
  plant is caught, and the tree comes back clean.
- `make setup` on a fresh clone switches the git hooks on; the session-start hook confirms it.
- An attempt to `git commit --no-verify` from the session is refused, and the refusal is shown.
- Every ledger exists and is empty.
- Every row of `CONSTRAINTS.md` marked "to build" names a command that now exists, and the row says so.

## Maintenance cadence

| When | What runs |
|---|---|
| Every edit | Lint and format on the touched file (hook). |
| End of a turn, or every commit | Contracts, types and dependencies at their one local stage; the harness gate and the debt ratchet at commit. |
| Every push | Everything, tests included, and the reviewer reports the paths need. |
| Every spec change | Re-render contracts and agent rules, decision record, adversarial review. |
| Every tool upgrade | A commit that bumps the lock alone. New findings are fixed or recorded with a reason, never silenced in place. The plants re-run. |
| Weekly (scheduled) | Plants, the harness audit and its auditor, dependency audit, knip and vulture reports, ledger counts: one short report of what moved. |
