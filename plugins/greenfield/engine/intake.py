"""Read the intake file the skill writes, refuse what the conventions forbid, and derive the rest."""

from __future__ import annotations

import json
import keyword
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

PY_SURFACES = ("cli", "http", "mcp", "jobs", "agent_tools")
ALL_SURFACES = (*PY_SURFACES, "web")
ROLES = ("ops", "render", "rules", "store", "model")
FIXED = ("kernel", "catalog", "flows", "adapters", "surfaces", "boot")
FORBIDDEN_NAMES = ("utils", "helpers", "common", "shared", "misc", "base", "core", "manager", "lib", "service")
FORBIDDEN_VERBS = ("process", "handle", "manage", "do")
DATABASES = {"postgres": "psycopg", "sqlite": "sqlite3", "none": None}
FRAMEWORK_DEFAULTS = {"http": "fastapi", "mcp": "fastmcp", "cli": "typer"}
# Top-level import names that mean an adapter calls a model, which switches the agents kit on.
MODEL_SDKS = ("anthropic", "openai", "claude_agent_sdk", "google", "litellm", "mistralai", "cohere", "groq")
HARNESS_KEYS = (
    "what_it_is",
    "who_uses_it",
    "today_instead",
    "failure_in_a_year",
    "goals",
    "not_this",
    "floors",
    "first_stage",
    "first_stage_goal",
    "first_gate_slug",
    "first_gate_demo",
    "first_gate_tried_to_break",
    "first_gate_acceptance",
    "later_gates",
    "interview_transcript",
)
MIN_FLOW_NOUNS = 2  # a flow spans nouns; one noun's use case is that noun's operation
SNAKE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")
SLUG = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
TOP_LEVEL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
FILE_PATH = re.compile(r"docs/|[A-Za-z0-9_-]+\.md([^A-Za-z]|$)")  # what serial-build's canon check refuses
ANY_DATE = re.compile(r"[12][0-9]{3}-[01][0-9]-[0-3][0-9]")
# Harness values that land in serial-build's standing documents, where its canon check refuses dates and paths.
STANDING = (
    "what_it_is",
    "who_uses_it",
    "today_instead",
    "failure_in_a_year",
    "goals",
    "not_this",
    "first_stage_goal",
    "first_gate_demo",
    "first_gate_builds",
    "first_gate_tried_to_break",
    "first_gate_acceptance",
    "first_gate_qa",
    "first_gate_decided",
    "first_gate_open",
    "first_gate_decide_by_proof",
    "later_gates",
    "open_questions",
)
REMOTES = ("created", "to-create", "none")
PASCAL = re.compile(r"^[A-Z][A-Za-z0-9]*$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
OWNER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")


class IntakeError(Exception):
    """The intake breaks one or more conventions; the message lists every problem."""


@dataclass(frozen=True)
class Noun:
    name: str
    purpose: str
    owns: tuple[str, ...]
    operations: tuple[str, ...]
    roles: tuple[str, ...]
    depends_on: tuple[str, ...]
    screens: bool

    @property
    def title(self) -> str:
        return "".join(part.capitalize() for part in self.name.split("_"))


@dataclass(frozen=True)
class Flow:
    name: str
    purpose: str
    uses: tuple[str, ...]


@dataclass(frozen=True)
class Adapter:
    name: str
    wraps: str
    implements: str
    purpose: str


@dataclass(frozen=True)
class Project:
    name: str
    slug: str
    package: str
    summary: str
    python: str
    database: str
    date: str
    surfaces: tuple[str, ...]
    driver: str | None
    frameworks: dict[str, str]
    lazy: tuple[str, ...]
    nouns: tuple[Noun, ...]
    flows: tuple[Flow, ...]
    adapters: tuple[Adapter, ...]
    principals: tuple[str, ...]
    spend: tuple[str, ...]
    first_operation: str
    rejected: tuple[str, ...]
    reopens: str
    addons: dict[str, bool]
    owner_name: str
    owner_writing: str
    repo: dict[str, str]
    harness: dict[str, str] = field(default_factory=dict)

    @property
    def py_surfaces(self) -> tuple[str, ...]:
        return tuple(s for s in self.surfaces if s in PY_SURFACES)

    @property
    def web(self) -> bool:
        return "web" in self.surfaces

    @property
    def first_noun(self) -> Noun:
        return self.noun(self.first_operation.split(".")[0])

    def noun(self, name: str) -> Noun:
        return next(n for n in self.nouns if n.name == name)

    @property
    def operations(self) -> tuple[str, ...]:
        return tuple(op for n in self.nouns for op in n.operations)

    @property
    def kits(self) -> tuple[str, ...]:
        """The add-on kits the surfaces and adapters call for: cli, mcp, agents."""
        out = [k for k in ("cli", "mcp") if k in self.surfaces]
        if "agent_tools" in self.surfaces or any(a.wraps.split(".")[0] in MODEL_SDKS for a in self.adapters):
            out.append("agents")
        return tuple(out)

    @property
    def screen_nouns(self) -> tuple[Noun, ...]:
        return tuple(n for n in self.nouns if n.screens) if self.web else ()


def _strs(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value] if isinstance(value, list) else []


def _text(raw: dict, key: str, default: str = "") -> str:
    value = raw.get(key, default)
    return value.strip() if isinstance(value, str) else default


def _sentence(kind: str, raw: dict, key: str, problems: list[str]) -> str:
    """Prose that becomes a Python docstring: one line, ending in a period, no quote or backslash."""
    text = " ".join(_text(raw, key).split())
    if '"' in text or "\\" in text:
        problems.append(f"{kind}: {key} may not contain a double quote or a backslash; it becomes a docstring")
    if text and not text.endswith((".", "!", "?")):
        text += "."
    return text


def _name_problems(kind: str, name: str) -> list[str]:
    if not SNAKE.match(name):
        return [f"{kind} {name!r} is not snake_case (lowercase words joined by single underscores)"]
    if keyword.iskeyword(name) or name in FORBIDDEN_NAMES or name in FIXED:
        return [f"{kind} {name!r} is a reserved or forbidden name"]
    return []


def _cycle(nouns: list[Noun]) -> list[str] | None:
    """A dependency ring among the nouns, if there is one."""
    deps = {n.name: n.depends_on for n in nouns}
    state: dict[str, int] = {}

    def visit(name: str, path: list[str]) -> list[str] | None:
        state[name] = 1
        for dep in deps.get(name, ()):
            if state.get(dep) == 1:
                return [*path, name, dep]
            if dep not in state and (ring := visit(dep, [*path, name])):
                return ring
        state[name] = 2
        return None

    for name in deps:
        if name not in state and (ring := visit(name, [])):
            return ring
    return None


def _nouns(raw: list, database: str, problems: list[str]) -> list[Noun]:
    nouns: list[Noun] = []
    for row in raw:
        name = _text(row, "name")
        problems += _name_problems("noun", name)
        roles = _strs(row.get("roles")) or ["ops", "model"]
        owns = _strs(row.get("owns"))
        ops = _strs(row.get("operations"))
        if owns and "store" not in roles:
            roles.append("store")
        roles = [r for r in ROLES if r in roles]
        problems += [
            f"noun {name}: role {r!r} is not one of {ROLES}" for r in _strs(row.get("roles")) if r not in ROLES
        ]
        if not {"ops", "model"} <= set(roles):
            problems.append(f"noun {name}: every noun has ops and model")
        if "store" in roles and not owns:
            problems.append(f"noun {name}: a store needs at least one owned table in owns")
        if owns and database == "none":
            problems.append(f"noun {name}: owns tables but the project has no database")
        if not ops:
            problems.append(f"noun {name}: declares no operations; a noun is something acted on")
        for op in ops:
            subject, _, verb = op.partition(".")
            if subject != name or not SNAKE.match(verb):
                problems.append(f"noun {name}: operation {op!r} is not {name}.<verb>")
            elif verb in FORBIDDEN_VERBS:
                problems.append(f"noun {name}: verb {verb!r} says nothing; name what happens")
        problems += [f"noun {name}: table {t!r} is not snake_case" for t in owns if not SNAKE.match(t)]
        nouns.append(
            Noun(
                name,
                _sentence(f"noun {name}", row, "purpose", problems),
                tuple(owns),
                tuple(ops),
                tuple(roles),
                tuple(_strs(row.get("depends_on"))),
                bool(row.get("screens", True)),
            )
        )
    return nouns


def _relations(nouns: list[Noun], problems: list[str]) -> None:
    names = [n.name for n in nouns]
    problems += [f"noun {n} is declared twice" for n in set(names) if names.count(n) > 1]
    for noun in nouns:
        problems += [f"noun {noun.name} depends on unknown noun {d!r}" for d in noun.depends_on if d not in names]
        if noun.name in noun.depends_on:
            problems.append(f"noun {noun.name} depends on itself")
    if ring := _cycle(nouns):
        problems.append(f"nouns depend on each other in a ring: {' -> '.join(ring)}")
    tables = [t for n in nouns for t in n.owns]
    problems += [f"table {t!r} is owned by more than one noun" for t in set(tables) if tables.count(t) > 1]
    ops = [op for n in nouns for op in n.operations]
    problems += [f"operation {op!r} is declared twice" for op in set(ops) if ops.count(op) > 1]


def _flows(raw: list, ops: set[str], problems: list[str]) -> list[Flow]:
    flows = []
    for row in raw:
        name, uses = _text(row, "name"), _strs(row.get("uses"))
        problems += _name_problems("flow", name)
        problems += [f"flow {name}: uses undeclared operation {u!r}" for u in uses if u not in ops]
        if len({u.split(".")[0] for u in uses}) < MIN_FLOW_NOUNS:
            problems.append(f"flow {name}: uses one noun at most; that is an operation of the noun, not a flow")
        flows.append(Flow(name, _sentence(f"flow {name}", row, "purpose", problems), tuple(uses)))
    return flows


def _adapters(raw: list, nouns: list[str], problems: list[str]) -> list[Adapter]:
    adapters = []
    for row in raw:
        name, wraps, implements = _text(row, "name"), _text(row, "wraps"), _text(row, "implements")
        problems += _name_problems("adapter", name)
        if name in nouns:
            problems.append(f"adapter {name!r} has a noun's name")
        if not TOP_LEVEL.match(wraps):
            problems.append(
                f"adapter {name}: wraps {wraps!r} must be a top-level import name (google, not google.genai): "
                "import-linter sees outside packages only at the top level"
            )
        if not PASCAL.match(implements):
            problems.append(f"adapter {name}: implements {implements!r} is not a PascalCase protocol name")
        adapters.append(Adapter(name, wraps, implements, _sentence(f"adapter {name}", row, "purpose", problems)))
    names = [a.name for a in adapters]
    problems += [f"adapter {n} is declared twice" for n in set(names) if names.count(n) > 1]
    return adapters


def _surfaces(raw: object, problems: list[str]) -> list[str]:
    given = [s for s, on in raw.items() if on] if isinstance(raw, dict) else _strs(raw)
    problems += [f"surface {s!r} is not one of {ALL_SURFACES}" for s in given if s not in ALL_SURFACES]
    surfaces = [s for s in ALL_SURFACES if s in given]
    if not any(s in PY_SURFACES for s in surfaces):
        problems.append(f"declare at least one way in: {PY_SURFACES}")
    if "web" in surfaces and "http" not in surfaces:
        problems.append("the web front end reaches the backend only through the http surface; declare http")
    return surfaces


def _harness(raw: dict, problems: list[str]) -> dict[str, str]:
    harness = {k: str(v) for k, v in raw.items() if isinstance(v, str | int)}
    problems += [f"harness: {k} is required when serial_build is on" for k in HARNESS_KEYS if not harness.get(k)]
    if "Break it:" not in harness.get("first_gate_demo", "Break it:"):
        problems.append("harness: first_gate_demo must end with a 'Break it:' step for the owner")
    for key in ("first_gate_slug", "first_stage"):
        if harness.get(key) and not SLUG.match(harness[key]):
            problems.append(f"harness: {key} must be a lowercase hyphenated slug")
    if harness.get("later_gates") and not any(
        line.startswith("Later:") for line in harness["later_gates"].splitlines()
    ):
        problems.append("harness: later_gates must open with a line starting 'Later:'")
    for key in STANDING:
        value = harness.get(key, "")
        if ANY_DATE.search(value):
            problems.append(f"harness: {key} carries a date; serial-build keeps dates out of its standing documents")
        if FILE_PATH.search(value):
            problems.append(f"harness: {key} names a file path; serial-build keeps paths out of its standing documents")
    return harness


def _repo(raw: dict, problems: list[str]) -> dict[str, str]:
    repo = {k: str(v) for k, v in raw.items() if isinstance(v, str)}
    if repo.get("org") and not OWNER.match(repo["org"]):
        problems.append(f"repo: owner {repo['org']!r} is not a GitHub owner name")
    if repo.get("name") and not re.match(r"^[A-Za-z0-9._-]+$", repo["name"]):
        problems.append(f"repo: name {repo['name']!r} is not a GitHub repository name")
    if repo.get("visibility", "private") not in {"private", "public"}:
        problems.append("repo: visibility is private or public")
    repo.setdefault("visibility", "private")
    repo.setdefault("remote", "to-create" if repo.get("org") else "none")
    if repo["remote"] not in REMOTES:
        problems.append(f"repo: remote is one of {REMOTES}")
    if repo["remote"] != "none" and not repo.get("org"):
        problems.append("repo: a remote needs an org (the GitHub owner)")
    return repo


def _homes(driver: str | None, adapters: list[Adapter], frameworks: dict[str, str], problems: list[str]) -> None:
    """One outside package, one home: two homes for one package leave no import legal."""
    homes = ([(driver, "the database driver")] if driver else []) + [(a.wraps, f"adapter {a.name}") for a in adapters]
    homes += [(lib, f"the {surface} surface") for surface, lib in frameworks.items()]
    for package in {pkg for pkg, _ in homes}:
        owners = [who for pkg, who in homes if pkg == package]
        if len(owners) > 1:
            problems.append(f"{package} is given two homes ({', '.join(owners)}); give it one, or one adapter")


def load(path: Path) -> Project:
    """Read and check the intake; raise IntakeError naming every problem at once."""
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise IntakeError(f"- the intake cannot be read as JSON: {error}") from error
    if not isinstance(raw, dict):
        raise IntakeError("- the intake must be one JSON object")
    problems: list[str] = []
    proj = raw.get("project", {})
    package, slug = _text(proj, "package"), _text(proj, "slug")
    problems += _name_problems("package", package)
    if package in sys.stdlib_module_names:
        problems.append(f"package {package!r} shadows the standard library module of that name")
    python = _text(proj, "python", "3.12")
    if not re.match(r"^3\.(1[2-9]|[2-9][0-9])$", python):
        problems.append(f"python {python!r}: the toolkit needs 3.12 or later")
    summary = _sentence("project", proj, "summary", problems)
    if not SLUG.match(slug):
        problems.append(f"project slug {slug!r} must be lowercase letters, digits and hyphens")
    database = _text(proj, "database", "postgres")
    if database not in DATABASES:
        problems.append(f"database {database!r} is one of {sorted(DATABASES)}")
    date = _text(raw, "date")
    if not DATE.match(date):
        problems.append("date must be YYYY-MM-DD")
    surfaces = _surfaces(raw.get("surfaces", []), problems)
    nouns = _nouns(raw.get("nouns", []), database, problems)
    if not nouns:
        problems.append("declare at least one noun")
    if "web" in surfaces and nouns and not any(n.screens for n in nouns):
        problems.append("the web front end needs at least one noun with screens")
    _relations(nouns, problems)
    ops = {op for n in nouns for op in n.operations}
    flows = _flows(raw.get("flows", []), ops, problems)
    adapters = _adapters(raw.get("adapters", []), [n.name for n in nouns], problems)
    clash = {f.name for f in flows} & {n.name for n in nouns}
    problems += [f"{c!r} is both a flow and a noun" for c in clash]
    first = _text(raw, "first_operation") or (nouns[0].operations[0] if nouns and nouns[0].operations else "")
    if first not in ops:
        problems.append(f"first_operation {first!r} is not a declared operation")
    authority = raw.get("authority", {})
    spend = _strs(authority.get("spend"))
    problems += [f"authority: spend names undeclared operation {s!r}" for s in spend if s not in ops]
    externals = raw.get("externals", {})
    frameworks = {s: FRAMEWORK_DEFAULTS[s] for s in surfaces if s in FRAMEWORK_DEFAULTS}
    frameworks.update({k: str(v) for k, v in externals.get("surface_frameworks", {}).items() if k in surfaces})
    addons = {
        k: bool(raw.get("addons", {}).get(k, d))
        for k, d in (("serial_build", False), ("agent_skills", False), ("factory", False))
    }
    owner = raw.get("owner", {})
    harness = _harness(raw.get("harness", {}), problems) if addons["serial_build"] else {}
    if addons["serial_build"] and not _text(owner, "name"):
        problems.append("owner.name is required with serial_build: the person who runs each demo")
    repo = _repo(raw.get("repo", {}), problems)
    driver = _text(externals, "database_driver") or DATABASES.get(database)
    _homes(driver, adapters, frameworks, problems)
    problems += [
        f"externals: lazy {name!r} is not a top-level import name"
        for name in _strs(externals.get("lazy"))
        if not TOP_LEVEL.match(name)
    ]
    if problems:
        raise IntakeError("\n".join(f"- {p}" for p in problems))
    decisions = raw.get("decisions", {})
    return Project(
        name=_text(proj, "name") or slug,
        slug=slug,
        package=package,
        summary=summary,
        python=python,
        database=database,
        date=date,
        surfaces=tuple(surfaces),
        driver=driver,
        frameworks=frameworks,
        lazy=tuple(_strs(externals.get("lazy"))),
        nouns=tuple(nouns),
        flows=tuple(flows),
        adapters=tuple(adapters),
        principals=tuple(_strs(authority.get("principals")) or ["operator"]),
        spend=tuple(spend),
        first_operation=first,
        rejected=tuple(_strs(decisions.get("rejected"))),
        reopens=_text(decisions, "reopens"),
        addons=addons,
        owner_name=_text(owner, "name"),
        owner_writing=_text(owner, "writing"),
        repo=repo,
        harness=harness,
    )
