# The intake

## The noun test

A candidate is a noun when all three hold:

1. It owns state (tables) or a set of operations whose names share it as subject (`invoice.create`,
   `invoice.send`).
2. Someone does something to it in a sentence the business would say ("the operator voids an invoice").
3. Its job is not to coordinate nouns (that is a flow), carry requests (a way in), talk to the outside
   (an adapter) or be shared foundations (the kernel).

Split a noun when its operations stop sharing one subject or pass about twelve. Merge two when every
change touches both. Prefer three to six nouns at the start. A report that needs a join across nouns is
its own read-only noun.

Verbs: `create`, `show`, `list`, `update`, `archive` or `void`, plus the domain's own (`send`, `record`,
`reserve`). Never `process`, `handle`, `manage` or `do`.

Roles inside a noun, top to bottom:
- `ops`: one function per operation;
- `render`: outward forms;
- `rules`: decisions;
- `store`: its tables and SQL, the only importer of the database driver;
- `model`: frozen records and errors.

Every noun has `ops` and `model`. `store` comes with `owns`. Give `rules` and `render` only to nouns
that need them.

## The file

`intake.json`, one JSON object. The engine refuses anything outside these rules and names every problem
at once (exit 3).

```json
{
  "date": "YYYY-MM-DD",
  "project": {
    "name": "Billing",
    "slug": "billing",
    "package": "billing",
    "summary": "Two sentences: what it is and the problem it removes.",
    "python": "3.12",
    "database": "postgres"
  },
  "repo": {"org": "DMG-Venture-Studio", "name": "billing", "visibility": "private", "remote": "to-create"},
  "surfaces": ["cli", "http", "mcp", "jobs", "agent_tools", "web"],
  "externals": {"surface_frameworks": {"cli": "typer", "http": "fastapi", "mcp": "fastmcp"}, "lazy": ["anthropic"]},
  "nouns": [
    {"name": "invoice", "purpose": "One sentence.", "owns": ["invoices", "invoice_lines"],
     "operations": ["invoice.create", "invoice.send"], "roles": ["ops", "render", "rules", "store", "model"],
     "depends_on": ["customer"], "screens": true}
  ],
  "flows": [{"name": "month_end", "purpose": "One sentence.", "uses": ["invoice.send", "customer.show"]}],
  "adapters": [{"name": "email", "wraps": "httpx", "implements": "Mailer", "purpose": "One sentence."}],
  "authority": {"principals": ["operator", "scheduler"], "spend": ["payment.record"]},
  "first_operation": "customer.create",
  "decisions": {"rejected": ["- An alternative offered and not chosen: why."], "reopens": "What would make this wrong."},
  "addons": {"serial_build": true, "agent_skills": true, "factory": false},
  "owner": {"name": "Ada", "writing": "- Terse and technical.\n- Consequence first."},
  "harness": {},
  "secrets": {
    "manager": {"environments": ["dev", "staging", "prod"]},
    "credentials": [
      {"name": "ANTHROPIC_API_KEY", "vendor": "anthropic", "adapter": "drafting", "path": "/worker",
       "envs": ["staging", "prod"], "purpose": "The drafting adapter's calls to Claude."}
    ]
  }
}
```

| Field | Rule |
|---|---|
| `date` | Today, `YYYY-MM-DD`. |
| `project.slug` | Lowercase letters, digits and hyphens; the CLI command and the distribution name. |
| `project.package` | `snake_case` Python import name; never `utils`, `core`, `lib` or another forbidden name. |
| `project.database` | `postgres` (driver psycopg), `sqlite` (driver sqlite3) or `none` (no noun may own tables). |
| `repo.remote` | `created` (the skill made it), `to-create` (the first session runs `gh repo create`) or `none`. Omit `org` for no remote. |
| `surfaces` | At least one of `cli`, `http`, `mcp`, `jobs`, `agent_tools`; `web` needs `http`. |
| `externals.surface_frameworks` | Defaults `cli: typer`, `http: fastapi`, `mcp: fastmcp`. Each library gets a one-home contract on its first import. |
| `externals.lazy` | Heavy SDKs that may only be imported inside a function (ruff's `banned-module-level-imports`). |
| `nouns[].operations` | Each `name.verb` for this noun; at least one. |
| `nouns[].roles` | Subset of the five; `ops` and `model` always. Omitted: `ops`, `model`, plus `store` when `owns` is set. |
| `nouns[].depends_on` | Nouns whose `ops` and `model` this one may import. No rings. |
| `nouns[].screens` | With `web`: whether the noun gets a folder in the front end. At least one noun must. Default true. |
| `flows[].uses` | Declared operations from at least two nouns. |
| `adapters[].wraps` | The top-level import name of the outside library (`anthropic`, `httpx`). A model SDK switches the agents kit on. |
| `adapters[].implements` | The PascalCase protocol name the kernel declares for it. |
| `decisions.rejected` | Alternatives offered at intake and not chosen, each with why. These go into the first decision record. |
| `owner.name` | Required with serial-build: the person who runs each demo. |
| `secrets` | Optional; its presence switches the credentials kit on. Shaped exactly as `credentials.toml`, and refused by the same rules its `check` applies. |
| `secrets.manager` | `kind` is `infisical` (the default). `environments` defaults to dev, staging and prod; `rotate_days` to 90 outside production and 0 (rotate on events only) in it. `host` and `project_id` may stay empty until the Infisical project exists. |
| `secrets.credentials[]` | `name` is the UPPER_SNAKE variable the code reads. `vendor` is one of anthropic, replicate, workos, openai, stripe, github, railway or other; other needs `keys_page`, the https page where its keys are minted. `adapter`, when given, is a declared adapter, and an adapter wrapping a vendor SDK must have a row. `path` is the Infisical folder (default `/`); `envs` a subset of the manager's (default all). |

## The harness block (only with `serial_build: true`)

Every value is in the owner's plain words. These are required:
- `what_it_is`, `who_uses_it`, `today_instead`, `failure_in_a_year`;
- `goals`, `not_this` and `floors`, each as bullets, one `- ` line per item;
- `first_stage` (a slug) and `first_stage_goal`;
- `first_gate_slug` (a slug);
- `first_gate_demo`, which ends with a sentence starting `Break it:`;
- `first_gate_tried_to_break` and `first_gate_acceptance`;
- `later_gates`, which opens with "Later: one line each, until intake writes them out in full." and then
  lists `- slug: what the owner will be able to do` lines, with any further `## Stage: <slug>` headings
  each carrying a `Goal:` line;
- `interview_transcript`, the verbatim record of every question, its options and the answer.

Optional: `commit_policy`, `first_gate_builds`, `first_gate_qa`, `first_gate_decided`, `open_questions`
(`## slug` sections), `worktree_include`.

Keep file paths and dates out of every harness value except the transcript. The harness's canon check
refuses both in the design, the roadmap and the open questions.

The engine derives everything else the harness needs from the spec: the layout table, the commands, the
stack, the toolchain, the generated files, the code paths and the worktree links. The harness's
documents and the scaffold therefore say the same thing.
