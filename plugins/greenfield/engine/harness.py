"""serial-build's answers file and hook config, so its /serial-build:scope fills the project without asking again.

The owner's words come from the intake; everything about layout, commands and toolchain is derived from
the spec, so the harness's documents and this scaffold say the same thing.
"""

from __future__ import annotations

import json

import commands
import docs
from intake import Project

INBOX = "claude_outputs"


def _bullets(text: str) -> str:
    return "\n".join(
        line if line.startswith(("- ", "  ")) else f"- {line}" for line in text.strip().splitlines() if line
    )


def _stack(p: Project) -> str:
    db = {
        "postgres": "Postgres through psycopg, because the database holds the invariants only it can hold",
        "sqlite": "SQLite through the standard library, because one file is all this needs to start",
        "none": "No database yet; adding one is a spec change",
    }[p.database]
    out = [
        f"- Python {p.python} with uv, every tool pinned, because one command reproduces any machine.",
        f"- {db}.",
        f"- Ways in: {', '.join(s for s in p.py_surfaces)}, each generated from one catalog of operations, "
        "so they cannot disagree.",
    ]
    if p.web:
        out.append(
            "- A TypeScript front end that reaches the backend only through a client generated from the "
            "HTTP surface's OpenAPI document."
        )
    return "\n".join(out)


def _deployables(p: Project) -> str:
    out = [f"- The `{p.slug}` service, reached through {', '.join(p.py_surfaces)}."]
    if p.web:
        out.append(f"- The `{p.slug}` web front end.")
    return "\n".join(out)


def _architecture(p: Project) -> str:
    out = [
        "## backend",
        "",
        "**Every module's path comes from closed lists: a noun or a fixed package, and a role.** Nouns are the "
        "business's things, each a vertical slice with only the roles it needs; the import contracts, rendered "
        "from the spec, hold the direction of every import. The rules and their reasons are in the conventions "
        "document under docs/tech; the nouns were decided in See `architecture`, the first decision record.",
        "",
        "**Every surface is a projection of one operation catalog.** A command, a route and an agent's tool call "
        "are the same operation behind the same authority check, so a parity test can prove they agree.",
    ]
    if p.web:
        out += [
            "",
            "## web",
            "",
            "**The front end mirrors the backend's nouns and has one network path.** Noun "
            "folders hold the roles routes, ui, state and api; only api touches the generated client.",
        ]
    return "\n".join(out)


def _toolchain(p: Project) -> str:
    out = [
        f"**Python is pinned to {p.python} and every tool to an exact version through uv.** ruff, pyrefly, "
        "import-linter, deptry and pytest are dev dependencies, so a check means the same thing on every machine.",
        "",
        "**The checks are listed with their commands in the constraints file at the repository root.** Each is "
        "proven by a planted violation that the toolkit's prove_checks runs; a check without a caught plant is "
        "not trusted.",
    ]
    if p.web:
        out += [
            "",
            "**The front end pins TypeScript 6, Biome, dependency-cruiser, ls-lint and knip.** "
            "dependency-cruiser does not support TypeScript 7 yet.",
        ]
    return "\n".join(out)


def _generated(p: Project) -> str:
    out = (
        f"The import contracts file is rendered from the spec by the toolkit's renderer and committed, because "
        f"lint-imports reads it; re-render with `{commands.render_cmd(p, check=False)}`."
    )
    if p.web:
        out += (
            " The front end's API client is generated from the OpenAPI document with `npm run api` and "
            "committed, because the type check needs it before the backend runs."
        )
    return out


def answers(p: Project) -> dict[str, str]:
    """Every key serial-build's templates use, from the owner's words and the spec."""
    h = p.harness
    first = p.first_noun
    rows = "\n".join(f"| `{path}` | {holds} |" for path, holds in docs.roots(p))
    code_paths = ["src/**", "tests/**", "tools/**"] + (["web/src/**"] if p.web else [])
    product_paths = ["src/**", "pyproject.toml"] + (["web/src/**", "web/package.json"] if p.web else [])
    symlinks = [".venv"] + (["web/node_modules"] if p.web else [])
    floors = _bullets(h["floors"]) + "\n" + docs.FLOORS
    return {
        "project_name": p.name,
        "project_slug": p.slug,
        "date": p.date,
        "owner_name": p.owner_name,
        "owner_writing": _bullets(p.owner_writing or "Plain language, every term defined where it is used."),
        "what_it_is": h["what_it_is"],
        "who_uses_it": h["who_uses_it"],
        "today_instead": h["today_instead"],
        "failure_in_a_year": h["failure_in_a_year"],
        "goals": _bullets(h["goals"]),
        "not_this": _bullets(h["not_this"]),
        "stack": _stack(p),
        "deployables": _deployables(p),
        "floors": floors,
        "roots_table": rows,
        "test_convention": "pytest `tests/<noun>/` beside the package"
        + ("; the front end's tests beside their files in `web/src/`" if p.web else ""),
        "generated_files": _generated(p),
        "toolchain": _toolchain(p),
        "architecture_sections": _architecture(p),
        "commands": commands.block(p),
        "commit_policy": h.get("commit_policy")
        or (
            f"Commit finished, proven work without asking. Never move a gate to done before {p.owner_name} "
            "has run its demo."
        ),
        "code_paths": "\n".join(f'  - "{path}"' for path in code_paths),
        "product_paths": "\n".join(f'  - "{path}"' for path in product_paths),
        "inbox": INBOX,
        "first_stage": h["first_stage"],
        "first_stage_goal": h["first_stage_goal"],
        "first_gate_slug": h["first_gate_slug"],
        "first_gate_builds": h.get("first_gate_builds")
        or (
            f"The `{p.first_operation}` operation as one slice: its {first.name} roles, its migration if it owns "
            f"a table, and every way in it declares ({', '.join(p.py_surfaces)}), with its parity test."
        ),
        "first_gate_demo": h["first_gate_demo"],
        "first_gate_depends": "none.",
        "first_gate_decided": h.get("first_gate_decided")
        or ("the nouns, the ways in and the closed module lists (see `architecture`)."),
        "first_gate_decide_by_proof": h.get("first_gate_decide_by_proof") or "none.",
        "first_gate_open": h.get("first_gate_open") or "none.",
        "first_gate_qa": h.get("first_gate_qa")
        or (
            "every check in the constraints file passes; every plant is caught; the parity test shows the "
            "operation on each way in."
        ),
        "first_gate_tried_to_break": h["first_gate_tried_to_break"],
        "first_gate_acceptance": h["first_gate_acceptance"],
        "later_gates": h["later_gates"],
        "worktree_symlinks": json.dumps(symlinks),
        "worktree_include": h.get("worktree_include", ".env"),
        "open_questions": h.get("open_questions", ""),
        "scope_decided": (
            f"**{p.name}: {p.summary}**\n\n**The first gate is {h['first_gate_slug']}**, built on the operation "
            f"`{p.first_operation}`.\n\n**Built from nouns and one operation catalog** (see `architecture`)."
        ),
        "scope_rejected": "- The alternatives to the nouns and the ways in are in the architecture record "
        "(see `architecture`); one fact, one place.",
        "scope_reopens": p.reopens or "The nouns stop describing what the owner says the product does.",
        "interview_transcript": h["interview_transcript"],
    }


def config(p: Project) -> dict[str, object]:
    """`.claude/serial-build.json`: the hooks run this project's own checks."""
    contracts = f"{commands.render_cmd(p, check=True)} && PYTHONPATH=src uv run lint-imports --config contracts.toml"
    on_edit: list[dict[str, object]] = [  # file-scoped and fast: the edit stage holds only lint and format
        {
            "name": "ruff",
            "paths": ["src/**", "tests/**", "tools/**"],
            "run": 'uv run ruff check "$SB_FILE" && uv run ruff format --check "$SB_FILE"',
        },
    ]
    on_stop: list[dict[str, object]] = [  # the one local stage for whole-project checks
        {
            "name": "contracts, types, dependencies and tests",
            "paths": ["src/**", "tests/**", "tools/**", "project-spec.toml"],
            "run": f"{contracts} && uv run pyrefly check && uv run deptry src && uv run pytest -q",
        },
    ]
    generated: list[dict[str, str]] = [{"path": "contracts.toml", "regenerate": commands.render_cmd(p, check=False)}]
    if p.web:
        on_edit.append({"name": "web lint", "paths": ["web/src/*"], "run": 'cd web && npx biome lint "../$SB_FILE"'})
        on_stop.append(
            {
                "name": "web types and boundaries",
                "paths": ["web/src/*"],
                "run": "cd web && npx tsc -p . && npx depcruise src --config .dependency-cruiser.cjs",
            }
        )
        generated.append({"path": "web/src/generated/*", "regenerate": "cd web && npm run api"})
    return {
        "version": 1,
        "owner": {"name": p.owner_name},
        "inbox": INBOX,
        "generated": generated,
        "checks": {"on_edit": on_edit, "on_stop": on_stop},
        "red": {"test_paths": ["tests/*"] + (["web/src/*.test.ts"] if p.web else [])},
    }


def files(p: Project) -> dict[str, str]:
    if not p.addons["serial_build"]:
        return {}
    return {
        ".claude/serial-build.json": json.dumps(config(p), indent=2) + "\n",
        f"docs/decisions/sources/scoping-answers-{p.date}.json": json.dumps(answers(p), indent=2) + "\n",
    }
