# Add-ons and kits: what each does, how they fit, what was proven

Each was installed into a project the engine generated, and checked against it on 8 October 2026.
Explain them to the user from here, in one line each, before asking.

## serial-build, the harness (optional, recommended when one person accepts the work)

DMG-Venture-Studio/serial-build-harness, plugin `serial-build@serial-build-harness`.

**What it does.** It builds the product one gate at a time. A gate is a slice the owner runs and
judges. Every gate is attacked by a fresh agent in its own worktree before it ships. A gate reaches
`docs/done.md` only through a script, after the owner says the acceptance sentence.

**How it fits.** Its `/serial-build:scope` normally interviews the owner. When `.claude/serial-build.json`
and a saved answers file already exist, it fills the missing files from them without asking again. The
engine writes both from this skill's interview and from the spec. The harness's own templates then
render in the first session, at whatever version is installed.

Proven against the harness at commit 60454e1:
- its `detect-state.sh` reports the scaffold as `scoped`, and `check-config.sh` passes;
- `render.sh` writes only new files, plus two merges:
  - `.claude/settings.json` gains the `worktree` block, and the plugin declarations and denies are kept;
  - `.gitignore` gains five lines;
- `check-canon.sh` passes all ten checks, including on the engine's own decision record.

**Division of labour.**
- The harness owns the lifecycle: gates, the roadmap, done, red-lane attacks and intake.
- The scaffold owns the architecture and the checks.
- The harness's edit and stop hooks run the scaffold's commands (ruff and the contracts on edit; types,
  deptry and the tests at stop), so the first session does not build second copies of those hooks.
- The walking skeleton becomes the first gate.
- The harness calls a slice of the product a gate. This scaffold calls a mechanical check a check, so
  the two words never collide.

## agent-skills (recommended)

addyosmani/agent-skills, plugin `agent-skills@addy-agent-skills`.

**What it does.** Engineering technique skills: test-driven development, debugging, code review,
security, API design and others. It also ships lifecycle skills: spec, plan, build and ship.

**How it fits with serial-build.** The technique skills apply inside any slice. The lifecycle skills
conflict with serial-build:
- `planning-and-task-breakdown` and `spec-driven-development` write `tasks/plan.md`, `tasks/todo.md`
  and `SPEC.md`, a second plan beside serial-build's one active plan;
- `/build auto` and `/ship` move work outside the harness's ledger.

The settings `skillOverrides` key does not apply to plugin skills, so the engine writes permission
denies instead.

Proven in a headless session on the generated project:
- `Skill(agent-skills:planning-and-task-breakdown)` is refused with "Skill execution blocked by
  permission rules";
- an undenied skill (`test-driven-development`) still launches;
- a typed `/agent-skills:plan` still expands its command text, so the engine also denies writes to
  `tasks/**` and `SPEC.md`; a Write there is refused.

A shell redirect would still get past the deny. That is defence in depth, not a wall.

**Without serial-build** nothing is denied, and agent-skills' lifecycle is the lifecycle.

Its `constraint-driven-development` skill reads an existing `CONSTRAINTS.md` instead of interviewing.
The engine writes that file in its format: the floor, every check with its command, and the exceptions
table.

## factory (optional, off by default)

addyosmani/factory, an installer, not a plugin. Its own advice: install it "when queue state, handoffs,
independent verification, or back-pressure solve a problem you have actually observed". On day zero
none has been observed. Say so, and recommend turning it on later.

**What it does.** GitHub issues become a queue. Scheduled cloud routines triage the issues, implement
small charter-permitted items, verify them and open draft pull requests. A person merges every one.

**How it fits with serial-build.** Both would hold the queue and both define "done", so running both as
general queues gives two sources of truth. They coexist only with a split:
- serial-build owns everything the owner must run to accept: features, the roadmap, demos;
- factory owns automatable maintenance: dependency bumps, lint and type fixes, docs, single-file fixes
  with a failing test;
- a `factory:ready-to-spec` issue goes to `/serial-build:intake`.

The bootstrap prompt pre-fills the charter that way and leaves `CHARTER_STATUS: incomplete` for the
owner.

Proven by installing it into a generated project:
- the installer skips exactly `CLAUDE.md` and `.claude/settings.json`, so its rules section and its
  merge-blocking hook must be merged by hand;
- its stock gate script ran whatever ruff (0.16.8, against the pinned 0.16.10) and mypy were on the
  path, never pyrefly and never the front end, so the bootstrap rewrites the script's Python branch to
  this project's commands.

**Cloud routines load no plugins.** serial-build's hooks are off there, so the git hooks and CI must
hold every check. The enforcement document says this.

## The harness audit kit (always)

DMG's own kit, from the audit of agents-for-the-arts. It keeps the agent's documents and context
honest.

**What it does.** `tools/toolkit/harness_audit.py` uses only the standard library and makes no model
calls. It measures:
- what loads into every session;
- what instruction files make the agent read;
- paths the docs name that do not exist;
- duplicated text;
- code-style names with no code;
- state kept in prose;
- checks repeated across stages, and slow hooks;
- agent and skill use.

Against those measurements:
- `harness.toml` holds the budgets, which only go down;
- the `harness-auditor` agent judges what cannot be measured;
- `.github/workflows/harness-audit.yml` runs both weekly;
- `harness_issues.py` mirrors findings into GitHub issues;
- `tools/toolkit/weekly-harness-audit.md` is the weekly run as a prompt, for a scheduled task.

**How it fits.** Its `--gate` mode is a starter check with two plants: an always-loaded rule over the
budget, and one naming a missing file. It changed three things in the conventions:
- Hooks are proven by plants, not pinned by digest. The kit flags pinning.
- Each check runs at one local stage, then at push and in CI. The kit flags a check repeated at every
  stage. With serial-build, the edit hook runs ruff on the edited file only. The end-of-turn hook is the
  one local stage for the contracts, types, deptry and the tests.
- The architecture rule loads only when code is touched, so the always-loaded context stays inside the
  budget.

`harness.toml` is written per project:
- it excludes the verbatim decision sources and a vendored skill;
- it ignores two kinds of path that are meant not to exist yet: serial-build's in-flight plan and the
  auditor's local log;
- it does not count the owner's name as an unbuilt term.

Proven:
- The two scripts were brought under the starter ruff and pyrefly without one suppression. Their
  reports are identical to the originals' on about 45 repositories, and the kit's 10 plants still pass.
- Every fixture scaffold has no high or medium finding.
- The always-loaded budget starts at 20,000 bytes (about 5k tokens), double the kit's own default. After
  serial-build's render the busiest fixture loads 9,665 bytes, 5,290 of them serial-build's always-on
  rule, which leaves room for the first session. The budget only goes down from there.
- The vendored better-cli description is 431 characters against a 400 budget. That is a low finding,
  left as upstream wrote it.

## Kits (automatic, from the spec)

| Kit | When | What goes in the project | Proven |
|---|---|---|---|
| better-cli (yogin16/better-cli) | a `cli` way in | Its skill, vendored unmodified into `.claude/skills/better-cli/` with its Apache-2.0 licence and a notice | Its marketplace entry fails to install on Claude Code 2.1.294 ("source: Invalid input"); the same plugin installs from a corrected entry. Vendoring needs no install and loads in cloud sessions too. |
| mcp-legibility (DMG-Venture-Studio/mcp-legibility) | an `mcp` way in | The plugin declared in settings; an `mcp-surface` project skill with the server rules; a "to build" check row | Its static probe on a catalog-driven FastMCP surface reads the `instructions=` constant. It reports zero tools, flagging dynamic registration, and a missing resources finding. The skill tells the session both are expected or fixable. |
| agent-house (addyosmani/agent-house) | an `agent_tools` way in, or an adapter wrapping a model SDK | An `agent-runs` project skill: GenAI spans from the model adapter, OTLP/JSON traces per scenario, `agent-house ci` against a baseline; a "to build" check row | A trace written by the Python OpenTelemetry SDK through the skill's encoder scores in agent-house 0.1.2. `ci` exits 1 on a regression. Unknown model ids price at zero, which the skill warns about. |

agentwright, the studio's own plugin for designing agents, is named in the `agent-runs` skill when it is
installed. It is not declared in the project.
