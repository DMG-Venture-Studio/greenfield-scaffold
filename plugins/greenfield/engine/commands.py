"""The project's commands and checks, in one place, so every document and config names the same ones."""

from __future__ import annotations

from dataclasses import dataclass

from intake import Project


@dataclass(frozen=True)
class Check:
    dimension: str
    rule: str
    command: str
    runs_at: str
    status: str  # "starter" (works and is planted now) or "to build" (the first session builds it)


def render_cmd(p: Project, *, check: bool) -> str:
    flag = " --check" if check else ""
    return (
        f"uv run python tools/toolkit/render_import_contracts.py{flag} project-spec.toml contracts.toml src/{p.package}"
    )


def lines(p: Project) -> list[tuple[str, str]]:
    """The commands a session runs, each with its one-line purpose."""
    out = [
        ("uv sync", "tools"),
        ("uv run ruff check . && uv run ruff format --check .", "lint, format"),
        ("uv run pyrefly check", "types"),
        (render_cmd(p, check=True), "contracts match the spec"),
        ("PYTHONPATH=src uv run lint-imports --config contracts.toml", "import contracts"),
        ("uv run deptry src", "dependencies"),
        *([("uv run python tools/toolkit/credentials.py check", "credentials")] if "credentials" in p.kits else []),
        ("uv run pytest", "tests"),
        ("uv run python tools/toolkit/harness_audit.py --gate", "context budgets"),
        ("uv run python tools/toolkit/prove_checks.py plants.toml", "plants"),
    ]
    if p.web:
        out += [
            ("(cd web && npm install)", "web tools"),
            ("uv run python tools/toolkit/prove_checks.py web/plants.toml", "web plants"),
        ]
    return out


def _staged(p: Project, rows: list[Check]) -> list[Check]:
    """Each check at one local stage, then push and CI: the harness audit flags a check repeated locally."""
    edit = "edit, push, CI"
    local = "stop, push, CI" if p.addons["serial_build"] else "commit, push, CI"
    stages = {
        "Lint": edit,
        "Format": edit,
        "Web lint": edit,
        "Tests": "stop, push, CI" if p.addons["serial_build"] else "push, CI",
        "Debt ratchet": "commit, CI",
        "Plants": "weekly in CI; push when a check changes",
    }
    keep = {"Harness", "No bypass", "Web dead code", "MCP legibility", "Agent runs", "Credential age"}
    return [
        row
        if row.dimension in keep
        else Check(row.dimension, row.rule, row.command, stages.get(row.dimension, local), row.status)
        for row in rows
    ]


def block(p: Project) -> str:
    """The commands as a code block body, each followed by its purpose as a comment."""
    return "\n".join(f"{c}  # {why}" for c, why in lines(p))


def _credential_checks(p: Project) -> list[Check]:
    """The credentials kit's two rows: the static check now, the audit against Infisical for the first session."""
    if "credentials" not in p.kits:
        return []
    return [
        Check(
            "Credentials",
            "every adapter wrapping a vendor SDK has a row in `credentials.toml`, and nothing git would commit "
            "holds the shape of a key",
            "`uv run python tools/toolkit/credentials.py check`",
            "commit, push",
            "starter",
        ),
        Check(
            "Credential age",
            "every declared key is present in each of its environments and inside its rotation window",
            "`uv run python tools/toolkit/credentials.py audit`, signed in to Infisical through GitHub's OIDC",
            "weekly in CI",
            "to build",
        ),
    ]


def checks(p: Project) -> list[Check]:
    """Every check the project holds, with whether it works now or the first session builds it."""
    pkg = p.package
    out = [
        Check(
            "Lint",
            '`select = ["ALL"]`, reasoned ignores in `ruff.toml`',
            "`uv run ruff check .`",
            "edit, commit, push",
            "starter",
        ),
        Check("Format", "ruff's formatter", "`uv run ruff format --check .`", "commit, push", "starter"),
        Check("Types", "every module typed from its first commit", "`uv run pyrefly check`", "commit, push", "starter"),
        Check(
            "Architecture",
            "tiers, roles, noun independence, one home per outside package, surfaces as leaves, no cycles",
            "`PYTHONPATH=src uv run lint-imports --config contracts.toml`",
            "edit, commit, push",
            "starter",
        ),
        Check(
            "Contracts drift",
            "`contracts.toml` is the render of `project-spec.toml`",
            f"`{render_cmd(p, check=True)}`",
            "edit, commit, push",
            "starter",
        ),
        Check(
            "Dependencies",
            "imported means declared; declared means imported",
            "`uv run deptry src`",
            "commit, push",
            "starter",
        ),
        *_credential_checks(p)[:1],
        Check("Tests", "pass; a skipped database test is a failure", "`uv run pytest`", "push", "starter"),
        Check(
            "Harness",
            "the context every session loads stays under the budgets in `harness.toml`, and no always-loaded "
            "file names a path that does not exist",
            "`uv run python tools/toolkit/harness_audit.py --gate`",
            "commit, CI",
            "starter",
        ),
        Check(
            "Plants",
            "every check refuses its planted violation, and the tree comes back clean",
            "`uv run python tools/toolkit/prove_checks.py plants.toml`",
            "weekly; push when a check changes",
            "starter",
        ),
        Check(
            "One home",
            "a literal bound to constants in two modules, or spelled out where a constant names it",
            "the toolkit's one-home check",
            "commit, push",
            "to build",
        ),
        Check(
            "Ways in",
            f"no main guard, load-by-name or `python -m` outside `src/{pkg}/surfaces/`",
            "the toolkit's ways-in reader with ruff `banned-api`",
            "commit, push",
            "to build",
        ),
        Check(
            "Surface parity",
            "every operation on every surface it declares; committed OpenAPI, MCP tool list "
            "and CLI help equal what the catalog generates",
            "a parity test and three `--check` renders",
            "commit, push",
            "to build",
        ),
        Check(
            "Debt ratchet",
            "no ledger grows against `main`, no rule removed, no limit raised, unless the "
            "commit says `Debt-Raised: <reason>`",
            "the toolkit's ratchet in the commit-msg hook",
            "commit",
            "to build",
        ),
        Check(
            "No bypass",
            "`--no-verify`, `-n` and hooks-path overrides refused",
            "a Claude Code PreToolUse hook and the git hooks, each with a plant",
            "every command",
            "to build",
        ),
    ]
    if p.database != "none":
        out.insert(
            8,
            Check(
                "Table ownership",
                "every table in `migrations/` owned by one noun in the spec, and named only in that noun's store",
                "a migrations-versus-spec check",
                "commit, push",
                "to build",
            ),
        )
    if p.web:
        out += [
            Check("Web types", "strict", "`cd web && npx tsc -p .`", "commit, push", "starter"),
            Check(
                "Web lint",
                "no `fetch` outside `kernel/http`, no `any`, no `console`",
                "`cd web && npx biome check src`",
                "edit, commit, push",
                "starter",
            ),
            Check(
                "Web boundaries",
                "tiers, nouns independent, roles in one direction, one network path, no orphans",
                "`cd web && npx depcruise src --config .dependency-cruiser.cjs`",
                "commit, push",
                "starter",
            ),
            Check("Web names", "only role files inside a noun", "`cd web && npx ls-lint`", "commit, push", "starter"),
            Check(
                "Web dead code",
                "no unused files, exports or dependencies",
                "`cd web && npx knip`",
                "push, weekly",
                "to build",
            ),
            Check(
                "Client drift",
                "the generated client is what the OpenAPI document produces",
                "`cd web && npm run api` compared with the committed file",
                "commit, push",
                "to build",
            ),
        ]
    if "mcp" in p.kits:
        out.append(
            Check(
                "MCP legibility",
                "the server sends an `instructions=` block naming its entry-point tool",
                "mcp-legibility's static probe (`probe_connect.py --repo . --json`)",
                "push",
                "to build",
            )
        )
    out += _credential_checks(p)[1:]
    if "agents" in p.kits:
        out.append(
            Check(
                "Agent runs",
                "each agent scenario's trace scores at least 80 and no lower than its baseline",
                "`npx -y agent-house@0.1.2 ci <trace> --baseline <baseline> --min-score 80`",
                "push",
                "to build",
            )
        )
    return _staged(p, out)
