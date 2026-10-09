# Harness audit kit

The audit of agents-for-the-arts (2026-10-07), turned into a scaffolder piece. A script measures everything
measurable for free. A weekly agent judges the rest. Any finding the agent raises a third time has to come
with a check, so its job shrinks over time.

| File | Goes to (in a generated project) | What it is |
|---|---|---|
| `toolkit/harness_audit.py` | `tools/toolkit/` | The collector. Standard library only, no model calls. `--gate` mode runs in under a second for pre-commit; the full report covers 7 lenses; `--time-hooks` times every hook in a throwaway worktree. |
| `toolkit/test_harness_audit.py` | `tools/toolkit/` | 9 plants: each finding fires on its plant. Three of them are precision plants that must not produce a finding: conditional reads, navigation tables, commented commands. |
| `toolkit/harness_issues.py` | `tools/toolkit/` | Optional mirror to GitHub issues with `gh`. One rollup issue, whose comments are the dated review log. One issue per high finding, deduplicated by id and closed when the finding goes away, with at most 5 new issues a week. |
| `toolkit/test_harness_issues.py` | `tools/toolkit/` | The issue sync tested against a fake `gh`. |
| `harness.toml` | repo root | Budgets and conventions, which are also the auditor's memory of what has been settled. Numbers only go down. |
| `.claude/agents/harness-auditor.md` | `.claude/agents/` | The judgment pass: one question, five steps, at most 40 tool calls, flags and routes but never edits. |
| `.github/workflows/harness-audit.yml` | `.github/workflows/` | Every Monday. The collector always runs. The auditor runs when `vars.HARNESS_MODEL == 'true'`, and issues sync when `vars.HARNESS_ISSUES == 'true'`. |
| `prompts/weekly-harness-audit.md` | the scaffolder (the prompt for a scheduled task) | The weekly run as a scheduled task or a local session. A local session adds the transcripts, so agent and skill use comes from real calls. |
| `prompts/harness-bootstrap.md` | the scaffolder (brownfield) | The one-time deep pass on an existing repository: measure, parallel read, verify, write the audit, hand off lanes, lock in caps. |

Run the plants with `python3 toolkit/test_harness_audit.py && python3 toolkit/test_harness_issues.py`.
Before the collector joins the toolkit, bring it under the starter `ruff.toml` and pyrefly, as the other pieces are.
