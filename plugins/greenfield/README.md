# greenfield

Start a project whose architecture is fixed by a spec from the first commit, and whose checks already
pass, each proven by a planted violation. Invoke it from Claude (desktop or web) or from Claude Code
with `/greenfield:new-project`, optionally followed by a pitch.

## What happens

1. **Intake.** Claude reads the pitch and any documents you pick as briefs, then proposes:
   - the nouns, each with its operations, tables and roles;
   - flows and adapters;
   - the ways in: CLI, HTTP, MCP, jobs, agent tools, web.

   You confirm the nouns. Everything else is rendered from them. Then it asks about the repository
   (owner, name, private or public) and the add-ons.
2. **Generate.** A deterministic engine (`engine/scaffold.py`, Python 3.12, standard library only)
   writes the project into an empty folder:
   - `project-spec.toml`;
   - the `src/<package>/` skeleton;
   - `contracts.toml` rendered from the spec;
   - the strict `ruff.toml`, pinned tools, and `plants.toml` with one violation per check;
   - the toolkit;
   - `CONSTRAINTS.md`, the conventions and enforcement documents, and the first decision record;
   - the agent context and kits;
   - for the harness, its answers and config;
   - the bootstrap prompt.

   It commits and adds the remote. It refuses an intake that breaks a convention and names every problem.
3. **Remote.** It is created with a GitHub tool when one is connected. Otherwise the first session runs
   `gh repo create`.
4. **Hand-over.** You run one command in the project folder:
   `claude "$(cat docs/decisions/sources/<date>-bootstrap-prompt.md)"`. The first session pushes,
   installs the plugins, runs the harness's scope, builds the remaining enforcement in a fixed order, and
   finishes with evidence.

## Add-ons and kits

| | When | Effect |
|---|---|---|
| serial-build harness | optional | Gates the owner accepts, a red lane that attacks each gate, one ledger. Fills itself from the intake without a second interview. |
| agent-skills | optional | Technique skills. With the harness, its spec, plan and ship pieces are denied by permission rules. |
| factory | optional, off by default | The issue queue for automatable maintenance only. The bootstrap installs it last, merges the two files it skips, and points its gates at the pinned tools. |
| better-cli | the spec has a CLI | Vendored skill (its marketplace entry does not install). |
| mcp-legibility | the spec has MCP | Plugin plus an `mcp-surface` skill. |
| agent-house | an agent or a model adapter | An `agent-runs` skill: traced spans, scored runs, a baseline gate. |
| harness audit | always | `harness_audit.py`: context budgets, missing paths, duplicated text, repeated checks, as a commit gate and a weekly report. Includes the `harness-auditor` agent, the weekly workflow and `harness_issues.py`. |

`skills/new-project/references/integrations.md` records what was proven about each, and how.

## Requirements

Python 3.12 or later, or uv, which fetches it. Git. To create the remote from the session, a connected
GitHub tool; otherwise `gh` on your machine for the first session. The generated project needs uv,
and npm for a front end.

## Developing

From the repository root:

```
python3 tests/run.py                       # the audit kit's plants, refused intakes, then every fixture:
                                           # generate, every check passes, every plant caught, no serious audit finding
python3 tests/integrations.py --harness <serial-build-harness clone> --factory <factory clone>
claude plugin validate plugins/greenfield
```
