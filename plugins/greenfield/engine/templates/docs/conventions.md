# Conventions: nouns, roles, operations, surfaces

How {{project_name}} is shaped. It is written so a coding agent can follow it without judgment calls. Every
rule that matters has a check listed in `CONSTRAINTS.md`; this document says why. The project's own nouns,
operations, surfaces and adapters are in `project-spec.toml`, the one place they are declared.

## The model

A project is a small set of **nouns** (the business's things), each a vertical slice with the same few
**roles** inside it. Each noun exposes **operations** (`{{first_operation}}`), the only unit of behaviour. One
**catalog** indexes every operation, checks who may call it and hands it the resources it needs. Every
**surface** (CLI, HTTP, MCP, jobs, agent tools, and through HTTP the web front end) is a projection of that
catalog and holds no logic of its own. **Flows** combine operations across nouns. **Adapters** wrap outside
services behind protocols the kernel defines, and **boot** is the one place that wires them in. The
**kernel** is the floor everything stands on.

Every module's path answers two questions from closed lists: which package (a noun or one of the fixed
packages) and which role. An agent never invents a module name.

## Vocabulary

| Term | Means | Is not |
|---|---|---|
| **Noun** (vertical) | A thing the business keeps records about and acts on: customer, invoice, payment. One package. | A table, a screen, a service, a verb. |
| **Role** | The job a module does inside a noun: `ops`, `render`, `rules`, `store`, `model`. Closed list. | A free-form name (`helpers`, `utils`, `manager`). |
| **Operation** | One named act on one noun, `<noun>.<verb>`, declared once in the noun's `ops`. | A route, a command or a tool; those are its projections. |
| **Catalog** | The index of every operation, with the authority check and resource hand-off. | A place for logic. |
| **Flow** | A use case spanning nouns (month-end close, onboarding), calling operations through the catalog. | A way around the catalog. |
| **Adapter** | One outside service (email, payments, a model API) behind a kernel protocol. | Something a noun imports. |
| **Boot** | The composition root: builds adapters and hands them to the catalog. | Configuration scattered across modules. |
| **Surface** | A way in: CLI, HTTP, MCP, jobs, agent tools. A leaf; nothing imports it. | Somewhere to put "just a little" logic. |
| **Kernel** | Principals, the result envelope, errors, resource protocols, ids and clock. | A dumping ground; its member list is closed too. |
| **Slice** (delivery) | One operation end to end: its `ops` function, the roles under it, every surface it declares, its tests. The unit of a commit and of a parallel lane. | A layer, or half an operation. |
| **Check** | A command that refuses a violation: lint, types, the import contracts, the tests. Listed in `CONSTRAINTS.md`, each proven by a plant. | A rule written only in prose. |

## Which things are nouns

A candidate is a noun when all three hold:

1. It owns state (one or more tables) or a set of operations whose names share it as subject
   (create an invoice, send it, void it).
2. Someone does something to it in a sentence the business would say: "the operator voids an invoice".
3. Its job is not to coordinate nouns (a flow), carry requests (a surface), talk to the outside (an
   adapter) or be shared foundations (the kernel).

Granularity: a noun may own several tables (an invoice noun may own both the invoices table and the invoice lines table). Split a noun when
its operation names stop sharing one subject or its `ops` passes about twelve operations; merge two when
every change touches both. Adding a noun is a deliberate act: it changes `project-spec.toml`, re-renders the
contracts, and gets a decision record.

## Backend tiers (Python, package `{{package}}`)

Each tier imports only tiers below it. Nouns and adapters sit side by side and never import each other.

| Tier | Holds | May import |
|---|---|---|
| `__main__` | `python -m {{package}}` | surfaces |
| `surfaces/` | `cli`, `http`, `mcp`, `jobs`, `agent_tools`: projections of the catalog, independent of each other | boot, the catalog, the kernel, a noun's `model` for types |
| `boot.py` | The composition root: builds every adapter once and returns the resources | adapters, the kernel |
| `flows/` | Cross-noun use cases, one module each, calling operations through the catalog | the catalog, nouns' `model`, the kernel |
| `catalog/` | `index.py`: every operation by name, the authority check, resource hand-off | every noun's `ops` |
| nouns, `adapters/` | One package per noun; one module per adapter | the kernel; a noun also the `ops` and `model` of the nouns its spec entry names in `depends_on` |
| `kernel/` | `principals`, `envelope`, `errors`, `resources` (protocols), `ids`, `clock` | the standard library and pure helpers |

## Roles inside a noun

Top to bottom; each may import only the ones below it. A noun has only the roles it needs.

| Role | Holds | Never |
|---|---|---|
| `ops` | One function per operation, named `<noun>_<verb>`: input schema, grant, resources, the receipt it returns. Thin. | SQL, templates, outside calls except through a handed-in resource. |
| `render` | Outward forms of the noun's records: message bodies, exports, files, reports. | Writes to the database. |
| `rules` | Decisions: "is this allowed, and what is wrong with it". May read through `store`. | Writes, outside calls, model calls. |
| `store` | The noun's tables and all of its SQL; transactions; invariants only the database can hold. The only importer of the database driver. | Another noun's tables. |
| `model` | Frozen dataclasses for the noun's records, and its errors. | Imports from the rest of the noun. |
| `__init__.py` | One docstring: what the noun is. | Code. |

A role file past about 500 lines becomes a folder of the same name (`store/`), its modules named for the
tables or records they handle. It never becomes `store_helpers.py`.

## The operation catalog

The hinge that makes every surface behave the same. Each operation declares, once:

| Field | Example |
|---|---|
| name | `{{first_operation}}` |
| summary | "Email one invoice to its customer, once." |
| input and output schema | JSON Schema, or a dataclass the schema is generated from |
| grant | `{{first_operation}}`; principals hold sets of grants |
| effect | `read`, `write`, `spend` or `external`; `spend` needs its own grant and is never granted by default |
| resources | `["mailer"]`, protocols from `kernel/resources.py`, handed in by the catalog from boot |
| idempotency | the request field that makes a retry safe |
| surfaces | defaults to every surface; an operation may opt out of one, with a reason |

Every surface is generated from these declarations. A UI action, a CLI command and an agent's tool call are
the same operation behind the same authority check; a parity test proves it. The scaffold starts the catalog
empty: an operation enters it when its slice is built, so the catalog is what exists and the spec is what is
planned.

## Surfaces

| Surface | Shape |
|---|---|
| CLI | `{{slug}} <noun> <verb> --json`; data on stdout, diagnostics on stderr; the versioned envelope from `kernel/envelope.py`; nonzero exit on error; never prompts; every error names the next command. |
| HTTP | One route per operation (`POST /<noun>/<verb>`, or a generated REST mapping); OpenAPI 3.1 generated from the catalog and committed. |
| MCP | One tool per operation exposed to agents, named `<noun>_<verb>`; the summary and schema are the tool's; `spend` tools only for principals granted spend. The server is built with an `instructions=` block that names the entry-point tool and one thing the server is not for; an error returns the envelope with the next call to make. |
| Jobs | Schedules and event handlers that start an operation or a flow and record the run. |
| Agent tools | The catalog filtered by the agent's grants, for an in-process agent SDK. Every model call goes through an adapter, which records it as a span. |
| Web | A separate TypeScript package in `web/` that reaches the backend only through a client generated from the OpenAPI document. |

A surface module translates a transport to an operation call and back: argument parsing, status codes, the
envelope. If a surface needs a decision, the decision belongs in a noun.

## Front end (`web/`)

The same model, one level up. Each tier imports only tiers below it; nouns never import each other.

| Tier | Holds |
|---|---|
| `src/app/` | The shell, the router, and pages that compose several nouns |
| `src/nouns/<noun>/` | One folder per backend noun that has a screen, named exactly as the backend noun |
| `src/kernel/` | `http` (the one place `fetch` is called), `auth`, `design` (the design system), `errors`, `config` |
| `src/generated/` | The OpenAPI client types; never edited |

Roles inside a web noun, top to bottom: `routes` (pages), `ui` (components), `state` (queries, caches,
mutations), `api` (thin calls through the generated client, the noun's only network path). `ui` and
`routes` may grow into folders of PascalCase components. The app uses a noun through its `routes` and `ui`
only.

## Data

Migrations are numbered SQL files in `migrations/`. Every table is owned by exactly one noun, named in that
noun's `owns` in the spec, and only that noun's `store` mentions it. A read across nouns goes through the
other noun's operation, not a join into its tables; a report that needs a join is its own noun with a
read-only store over a view.

## Tests

`tests/<noun>/test_<role>.py`. `rules` tests are pure and fast. `store` tests run against a throwaway
database, and a skipped database test counts as a failure. `ops` tests cover schema, grant, resource and
receipt. Flows are tested end to end with fake adapters, which handed-in resources make trivial. Surface
tests are generated parity tests, not one test per operation per surface.

## Names

- Packages: nouns, singular, `snake_case`. Operations: `<noun>.<verb>`; functions in `ops`: `<noun>_<verb>`.
- Verbs: `create`, `show`, `list`, `update`, `archive` or `void`, plus the domain's own (`send`, `record`,
  `reserve`). Never `process`, `handle`, `manage`, `do`.
- Never a module or folder named `utils`, `helpers`, `common`, `shared`, `misc`, `base`, `core`, `manager`,
  `lib` or `service`. With closed lists they cannot appear, so no rule has to name them.
- Exceptions in plain words (`Refused`, `NotFound`); the kernel's are shared, a noun's own live in its
  `model`.
- Docstrings: one sentence saying what the thing is or does. A module docstring is what the rendered
  path-scoped rules show an agent, so it has to be true.

## Decisions

One decision record per new noun, adapter or surface, and per rule change:
`docs/decisions/YYYY-MM-DD-<slug>.md` with a `Date:` line and three sections, `## Decided`, `## Rejected`
(the alternatives, each with why) and `## Reopens if`. Records are append-only. The briefs, prompts and
interviews a record acted on are kept verbatim in `docs/decisions/sources/`.

## Where new code goes

1. New behaviour on a noun that exists: an operation in its `ops`, with whatever it needs in the roles
   below. No new file unless a role the noun lacks is needed.
2. Behaviour across nouns: a flow. If it only touches one noun, it is that noun's operation.
3. A new outside service: an adapter plus a protocol in `kernel/resources.py`, added to the spec.
4. A new noun, surface or adapter: a spec change first, then the contracts re-render, then the code.
5. Anything that does not fit: stop and ask. The lists are closed on purpose.
