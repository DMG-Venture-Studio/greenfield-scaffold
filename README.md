# greenfield-scaffold

A Claude plugin that starts a new project with its architecture fixed by a spec and its checks already
passing, each check proven by a planted violation. You describe the project, or point at the docs you
wrote while speccing it. You confirm the nouns. A deterministic engine writes the project, commits it,
creates the GitHub repository, and hands Claude Code a prompt for its first session.

```
/greenfield:new-project using the design doc and the ledger you wrote, scaffold it
```

## What it solves

- **Architecture drift from the first commit.** Left alone, a coding agent invents module names, imports
  across features and puts logic in its CLI or HTTP handlers. Here every module's path comes from closed
  lists, and the import rules are generated from the spec. A stray import fails a check instead of
  waiting for code review.
- **Checks nobody has proven.** Every check ships with a planted violation. A runner applies each one,
  confirms the check catches it, and restores the tree exactly. A check that has been switched off shows
  up as a plant that gets through.
- **Rebuilding check machinery in every repo.** The contracts renderer, the plant runner and the harness
  audit come in a pinned toolkit; they are never rewritten per project.
- **Ways in that disagree.** The CLI, HTTP, MCP, jobs, agent tools and the web front end are all
  projections of one catalog of operations, so they cannot disagree about what exists or who may call it.
- **Agent context that bloats or goes stale.** The harness audit measures four things: what loads into
  every session, docs that name files that don't exist, duplicated text, and checks repeated at every
  stage. Its budgets only go down.
- **Add-ons that fight each other.** One interview feeds the spec, the serial-build harness's answers and
  the checks list. The conflicts between the add-ons are resolved and tested.

## Install

In Claude Code:

```
/plugin marketplace add DMG-Venture-Studio/greenfield-scaffold
/plugin install greenfield@greenfield
```

In the Claude desktop app, install the `.plugin` file built from `plugins/greenfield/`. The command is
in Developing below.

## How a run goes

1. **Intake.** Claude reads your pitch, and any docs you name as briefs: files from the conversation,
   attachments, Project docs or a Claude Design hand-off prompt. It unpacks a zip of docs.
   - It asks about any open item in the briefs that changes the architecture.
   - It proposes the nouns (the business's things), their operations, flows, adapters and ways in.
     **You confirm the nouns**; everything else is rendered from them.
   - Then it covers the repository: owner, name, public or private.
   - Then the add-ons.
2. **Generate.** `engine/scaffold.py` (Python 3.12, standard library only) writes into an empty folder
   from the confirmed intake. An intake that breaks a convention is refused, with every problem named.
3. **Remote.** Created with a connected GitHub tool when there is one; otherwise the first session runs
   `gh repo create`.
4. **Hand-over.** From the project folder:
   `claude "$(cat docs/decisions/sources/<date>-bootstrap-prompt.md)"`. The first session:
   - pushes;
   - installs the declared plugins;
   - runs the harness scope if it is on;
   - builds the rest of the enforcement in a fixed order (check runner, git hooks, Claude Code hooks,
     project checks, agent context, CI);
   - finishes with evidence.

## What a generated project holds

```
project-spec.toml          the architecture, declared once: nouns, operations, ways in, adapters
contracts.toml             import contracts rendered from the spec (never edited by hand)
src/<package>/             kernel, catalog, flows, adapters, surfaces, boot, one package per noun
tests/                     pytest, tests/<noun>/test_<role>.py
tools/toolkit/             the pinned toolkit: contracts renderer, plant runner, harness audit
plants.toml                one planted violation per starter check (web/plants.toml with a front end)
ruff.toml                  select = ["ALL"], a short reasoned ignore list, limits, banned APIs
harness.toml               context budgets for the harness audit
CONSTRAINTS.md             every check, its command, when it runs, and whether it is built yet
docs/tech/                 the conventions, how they are enforced, and the threat model the checks defend against
docs/decisions/            dated decision records; sources/ keeps the briefs and the bootstrap prompt
.claude/                   path-scoped architecture rule, settings, kit skills, the harness auditor
.github/workflows/         the weekly harness audit
web/                       with a front end: TypeScript, dependency-cruiser, ls-lint, Biome
```

Inside a noun, a module is one of five roles: `ops`, `render`, `rules`, `store` or `model`. Each imports
only the roles below it, and nouns never import each other unless the spec says so. Every outside
package has one home: the database driver lives only in a store, and an SDK only in its adapter. The
full rules are in `plugins/greenfield/engine/templates/docs/conventions.md`.

## Add-ons and kits

| | When | What it brings |
|---|---|---|
| [serial-build](https://github.com/DMG-Venture-Studio/serial-build-harness) | optional | The owner accepts each slice by running it, and a red lane attacks each one before it ships. It fills itself from this intake without a second interview. |
| [agent-skills](https://github.com/addyosmani/agent-skills) | optional | Technique skills. With serial-build, its own plan, spec and ship skills are blocked so there is one plan. |
| [factory](https://github.com/addyosmani/factory) | optional, off by default | A GitHub-issue queue for automatable maintenance, with draft PRs a person merges. Installed last, with its gates pointed at the pinned tools. |
| [better-cli](https://github.com/yogin16/better-cli) | a CLI way in | Its skill, vendored with its licence. Its own marketplace entry does not install on Claude Code 2.1.294; this repo's marketplace lists it with a corrected entry. |
| [mcp-legibility](https://github.com/DMG-Venture-Studio/mcp-legibility) | an MCP way in | The plugin, plus a skill for building an MCP surface a cold agent can use. |
| [agent-house](https://github.com/addyosmani/agent-house) | an agent or a model adapter | A skill for tracing model calls, scoring runs and holding a baseline. |
| harness audit | always | Context budgets, missing paths, duplicated text, repeated checks, as a commit gate and a weekly report with an auditor agent. |

`plugins/greenfield/skills/new-project/references/integrations.md` records what was proven about each,
and how.

## Proof

| Suite | Shows |
|---|---|
| `python3 tests/run.py` | Covers the harness audit kit's 10 plants and 10 refused intakes, each refused for the right reason with nothing written. Then four fixture projects: a 3-noun Postgres app with a web front end and every add-on; an edge case; an MCP and agent-tools app; and a 1-noun CLI. Each passes ruff, format, pyrefly, the contracts and their drift check, deptry, pytest, the harness gate and `python -m <package>`. Each has no high or medium audit finding, and every plant is caught: 21 to 27 Python plants, plus 15 web plants with a front end. |
| `python3 tests/integrations.py --harness <clone> --factory <clone>` | serial-build's own scripts treat the scaffold as already scoped and render into it without overwriting anything. Its canon check passes 10 of 10, and the harness gate still passes afterwards. factory's installer skips exactly the two files the bootstrap prompt merges. Tested against serial-build-harness 60454e1 and factory 8af1165. |

## Requirements

- Python 3.12 or later, or uv, which fetches it.
- git.
- To create the remote from the session, a connected GitHub tool; otherwise `gh` on your machine.
- Generated projects need uv, and npm for a front end.

## Developing

```
python3 tests/run.py [fixture ...] [--no-web] [--keep DIR]
python3 tests/integrations.py --harness <serial-build-harness clone> --factory <factory clone>
claude plugin validate plugins/greenfield && claude plugin validate .
cd plugins/greenfield && zip -qr ../../greenfield.plugin . -x "*__pycache__*"    # the desktop .plugin
```

```
.claude-plugin/marketplace.json     this marketplace: greenfield, and better-cli with a working entry
plugins/greenfield/
  skills/new-project/               the skill and its references (intake schema, delivery, integrations)
  engine/                           scaffold.py and the generators, templates, starters, toolkit, vendor
tests/                              fixtures, refused intakes, the toolkit's own tests, integrations
```

## License

MIT, in `LICENSE`. The vendored better-cli skill keeps its Apache-2.0 licence and notice, in
`plugins/greenfield/engine/vendor/better-cli/`.
