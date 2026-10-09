# Toolkit {{version}}

Check machinery shared by every project the greenfield scaffolder starts. Copied in at a pinned version;
never edited per project. A change goes to the scaffolder, gets its own tests there, and arrives here as a
new version in its own commit.

| Piece | What it does | Run |
|---|---|---|
| `render_import_contracts.py` | Renders `contracts.toml` from `project-spec.toml`: tiers, roles, noun independence, catalog-only access from above, surfaces as leaves, one home per outside package, no test tooling in the runtime, no cycles. An outside package's contract appears with its first import, because lint-imports refuses to protect a package nothing imports. | `uv run python tools/toolkit/render_import_contracts.py [--check] project-spec.toml contracts.toml src/<package>` |
| `harness_audit.py` | Measures the agent's harness: what loads into every session and what instruction files make it read, paths the docs name that do not exist, duplicated text, code-style names with no code, state kept in prose, checks repeated across stages and slow hooks, and agent and skill use. Budgets come from `harness.toml`, which only go down. `--gate` checks the context budgets and the always-loaded files' paths in under a second, for the commit hook; `--time-hooks` times every hook in a throwaway worktree. No model calls. | `uv run python tools/toolkit/harness_audit.py [--gate] [--json r.json --md r.md] [--baseline last.json] [--time-hooks] [--transcripts <dir>]` |
| `harness_issues.py` | Mirrors a report into GitHub issues with `gh`: one rollup issue whose comments are the weekly log, one issue per high finding, closed when it disappears, at most five new a week. | `uv run python tools/toolkit/harness_issues.py r.json --markdown r.md [--findings auditor.json] [--dry-run]` |
| `weekly-harness-audit.md` | The weekly run as a prompt: collect, run the `harness-auditor` agent, deliver. Use it as a scheduled task's prompt or paste it into a session. | |
| `prove_checks.py` | Runs a plants file: the clean tree must pass every check; then each plant is applied alone, the named check must fail saying the expected words, and the tree is restored byte for byte, even when a check crashes. A failed preparation step counts as the check failing. | `uv run python tools/toolkit/prove_checks.py plants.toml` |

## The plants file

```toml
[[check]]
name = "contracts"
prepare = [["uv", "run", "python", "tools/toolkit/render_import_contracts.py", "--check", "..."]]
run = ["uv", "run", "lint-imports", "--config", "contracts.toml", "--no-cache"]
env = { PYTHONPATH = "src" }

[[plant]]
label = "a role imports a role above it"
file = "src/app/customer/model.py"
append = "from app.customer import ops\n"      # or create = "..." for a new file
expect = { check = "contracts", says = "Roles" }

[[plant]]
label = "an import ring"
edits = [{ file = "a.py", append = "..." }, { file = "b.py", append = "..." }]
expect = { check = "contracts", says = "No cycles" }
```

Hooks are proven by plants, not pinned by digest: a digest inside a check makes every hook edit a check
change, and the harness audit flags it.

ruff 0.16 prints rule names (`blind-except`), not codes, in its default output; plants match on names.

## Not here yet

These exist in the project the conventions came from, with that project's paths built in. Until they join
the toolkit, the first session builds the smallest version that passes its plants, under `tools/`, and
reports it back:

- the debt ratchet (ledgers may only shrink against `main`; `Debt-Raised:` trailer to grow one);
- the one-home check (a literal bound in two modules, or spelled out where a constant names it);
- the ways-in reader (main guards in any spelling, load by name or path, outside the surfaces);
- the agent-rules renderer (path-scoped rules from the spec and module docstrings, with `--check`);
- the new-module guard (a Write to a path off the closed lists is refused, with the layout shown).
