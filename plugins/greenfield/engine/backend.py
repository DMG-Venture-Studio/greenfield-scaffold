"""The Python skeleton: every fixed package, one package per noun with only its declared roles, typed."""

from __future__ import annotations

import json
import textwrap

from intake import Project

DEV_DEPENDENCIES = ("ruff==0.16.10", "import-linter==2.15", "pyrefly==1.3.2", "pytest==9.1.1", "deptry==0.25.1")

ROLE_DOCS = {
    "ops": "The {noun}'s operations, one function each, named {noun}_<verb>: {ops}.",
    "render": "Outward forms of a {noun}: message bodies, exports, files, reports.",
    "rules": "Decisions about a {noun}: whether something is allowed, and what is wrong with it.",
    "store": "The {noun}'s tables ({owns}) and all of their SQL; the only importer of the database driver.",
}

SURFACE_DOCS = {
    "cli": "The command line: `{slug} <noun> <verb> --json`, one command per operation in the catalog.",
    "http": "The HTTP surface: one route per operation, generated from the catalog; OpenAPI is committed.",
    "mcp": "The MCP surface: one tool per operation an agent may call, generated from the catalog.",
    "jobs": "Schedules and event handlers that start an operation or a flow and record the run.",
    "agent_tools": "The catalog filtered by an agent's grants, as tools for an in-process agent SDK.",
}

SURFACE_LISTING = {
    "cli": ("commands", '[name.replace(".", " ") for name in sorted(OPERATIONS)]'),
    "http": ("routes", '["/" + name.replace(".", "/") for name in sorted(OPERATIONS)]'),
    "mcp": ("tools", '[name.replace(".", "_") for name in sorted(OPERATIONS)]'),
    "jobs": ("operations", "sorted(OPERATIONS)"),
    "agent_tools": ("tools", '[name.replace(".", "_") for name in sorted(OPERATIONS)]'),
}


def _doc(text: str, indent: str = "") -> str:
    """A docstring within 110 columns: one line, or a summary sentence and a wrapped body."""
    width = 110 - len(indent)
    if len(text) + 6 <= width:
        return f'{indent}"""{text}"""\n'
    for mark in (". ", ": ", "; "):
        head, sep, rest = text.partition(mark)
        if sep and rest and len(head) + 7 <= width:
            body = textwrap.indent(textwrap.fill(rest[0].upper() + rest[1:], width=width), indent)
            return f'{indent}"""{head}.\n\n{body}\n{indent}"""\n'
    words = text.split()
    head = ""
    while words and len(head) + len(words[0]) + 8 <= width:
        head = f"{head} {words.pop(0)}".strip()
    body = textwrap.indent(textwrap.fill(" ".join(words), width=width), indent)
    return f'{indent}"""{head}\n\n{body}\n{indent}"""\n' if words else f'{indent}"""{head}"""\n'


def pyproject(p: Project) -> str:
    """The project file: no runtime dependency until code imports one; dev tools pinned."""
    scripts = f'\n[project.scripts]\n{p.slug} = "{p.package}.surfaces.cli:main"\n' if "cli" in p.surfaces else ""
    dev = ", ".join(f'"{d}"' for d in DEV_DEPENDENCIES)
    return f"""[project]
name = "{p.slug}"
version = "0.0.0"
description = {json.dumps(p.summary.split(". ")[0].rstrip("."))}
requires-python = ">={p.python}"
dependencies = []
{scripts}
[dependency-groups]
dev = [{dev}]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/{p.package}"]

[tool.pyrefly]
project-includes = ["src", "tests", "tools"]
search-path = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
# tests/<noun>/test_<role>.py repeats file names across nouns, so test modules are imported by path.
addopts = ["--import-mode=importlib"]

[tool.deptry]
known_first_party = ["{p.package}"]
"""


def _kernel(p: Project) -> dict[str, str]:
    k = f"src/{p.package}/kernel"
    protocols = "".join(
        f"\n\nclass {a.implements}(Protocol):\n" + _doc(a.purpose or f"What the {a.name} adapter does.", "    ")
        for a in p.adapters
    )
    if p.database != "none":
        protocols = (
            '\n\nclass Connection(Protocol):\n    """A database connection the catalog hands to an operation; '
            'only a noun\'s store uses it."""\n' + protocols
        )
    typing = "\nfrom typing import Protocol" if protocols else ""
    return {
        f"{k}/__init__.py": _doc("The floor: principals, the result envelope, errors and the resource protocols."),
        f"{k}/errors.py": _doc("The errors every package shares; a noun's own errors live in its model.")
        + '\n\nclass Refused(Exception):\n    """The caller may not do this; the message says why and what to '
        'send instead."""\n\n\nclass NotFound(Exception):\n    """No record has the id the caller gave."""\n',
        f"{k}/envelope.py": _doc("The one result shape every surface returns: data, or an error and the next step.")
        + "\nfrom dataclasses import dataclass, field\n\n\n@dataclass(frozen=True)\nclass Envelope:\n"
        '    """A versioned result: data on success, or the error and the call that would fix it."""\n\n'
        "    ok: bool\n    data: dict[str, object] = field(default_factory=dict)\n    error: str | None = None\n"
        "    next_step: str | None = None\n    version: int = 1\n",
        f"{k}/principals.py": _doc("Who is calling, and which operation grants they hold.")
        + "\nfrom dataclasses import dataclass\n\n\n@dataclass(frozen=True)\nclass Principal:\n"
        '    """A caller (a person, an agent or a schedule) and the grants it holds."""\n\n'
        "    name: str\n    grants: frozenset[str]\n\n    def may(self, grant: str) -> bool:\n"
        '        """Whether this principal holds the grant."""\n        return grant in self.grants\n',
        f"{k}/resources.py": _doc("The protocols operations ask for; boot builds the adapters that implement them.")
        + f"\nfrom dataclasses import dataclass{typing}\n{protocols}\n\n@dataclass(frozen=True)\nclass Resources:\n"
        '    """What boot built; the catalog hands each operation only the resources it names."""\n',
    }


def _catalog(p: Project) -> dict[str, str]:
    c = f"src/{p.package}/catalog"
    surfaces = ", ".join(f'"{s}"' for s in p.py_surfaces) + ("," if len(p.py_surfaces) == 1 else "")
    return {
        f"{c}/__init__.py": _doc("The index of every operation: the hinge every surface is generated from."),
        f"{c}/index.py": _doc("Every built operation by name: what it is, who may call it, where it is exposed.")
        + "\nfrom dataclasses import dataclass\nfrom typing import Literal\n\n\n@dataclass(frozen=True)\n"
        'class Operation:\n    """One operation\'s declaration; the function itself lives in its noun\'s ops."""\n\n'
        '    name: str\n    summary: str\n    grant: str\n    effect: Literal["read", "write", "spend", "external"]\n'
        f"    resources: tuple[str, ...] = ()\n    surfaces: tuple[str, ...] = ({surfaces})\n\n\n"
        "# An operation enters the catalog when its slice is built; project-spec.toml holds the plan.\n"
        "OPERATIONS: dict[str, Operation] = {}\n",
    }


def _surface(p: Project, name: str) -> str:
    noun, expr = SURFACE_LISTING[name]
    return (
        _doc(SURFACE_DOCS[name].format(slug=p.slug))
        + f"\nimport json\nimport sys\nfrom dataclasses import asdict\n\nfrom {p.package} import boot\n"
        f"from {p.package}.catalog.index import OPERATIONS\nfrom {p.package}.kernel.envelope import Envelope\n\n\n"
        f'def listing() -> list[str]:\n    """The {noun} this surface exposes, one per operation in the catalog."""\n'
        f"    return {expr}\n\n\n"
        "def main(argv: list[str] | None = None) -> int:\n"
        '    """Print what this surface exposes as an envelope; the transport itself is built per slice."""\n'
        "    boot.build()\n"
        "    arguments = sys.argv[1:] if argv is None else argv\n"
        f'    print(json.dumps(asdict(Envelope(ok=True, data={{"{noun}": listing(), "arguments": arguments}}))))\n'
        "    return 0\n"
    )


def _nouns(p: Project) -> dict[str, str]:
    files: dict[str, str] = {}
    for n in p.nouns:
        base = f"src/{p.package}/{n.name}"
        files[f"{base}/__init__.py"] = _doc(n.purpose or f"The {n.name}.")
        files[f"{base}/model.py"] = (
            _doc(f"The {n.name}'s records and its own errors.")
            + f"\nfrom dataclasses import dataclass\n\n\n@dataclass(frozen=True)\nclass {n.title}:\n"
            + _doc(n.purpose or f"One {n.name}.", "    ")
            + "\n    key: str\n"
        )
        for role in ("ops", "render", "rules", "store"):
            if role in n.roles:
                text = ROLE_DOCS[role].format(noun=n.name, ops=", ".join(n.operations), owns=", ".join(n.owns))
                files[f"{base}/{role}.py"] = _doc(text)
    return files


def files(p: Project) -> dict[str, str]:
    """Every backend file, by path from the project root."""
    pkg = f"src/{p.package}"
    entry = "cli" if "cli" in p.surfaces else p.py_surfaces[0]
    out = {
        "pyproject.toml": pyproject(p),
        ".python-version": f"{p.python}\n",
        f"{pkg}/__init__.py": _doc(f"{p.name}: {p.summary.split('. ')[0].rstrip('.')}."),
        f"{pkg}/__main__.py": _doc(f"`python -m {p.package}`: the {entry} surface.")
        + f"\nimport sys\n\nfrom {p.package}.surfaces import {entry}\n\nsys.exit({entry}.main(sys.argv[1:]))\n",
        f"{pkg}/boot.py": _doc("The composition root: builds each adapter once and hands the resources to the catalog.")
        + f"\nfrom {p.package}.kernel.resources import Resources\n\n\ndef build() -> Resources:\n"
        '    """Every resource an operation may ask for, built once."""\n    return Resources()\n',
        f"{pkg}/flows/__init__.py": _doc(
            "Use cases across nouns, one module each, calling operations through the catalog."
        ),
        f"{pkg}/adapters/__init__.py": _doc(
            "Outside services, one module each, behind a protocol in kernel.resources."
        ),
        f"{pkg}/surfaces/__init__.py": _doc(
            "The ways in, each a projection of the catalog; nothing imports a surface."
        ),
        "tests/test_catalog.py": _doc("The catalog holds only operations the spec declares.")
        + f"\nimport tomllib\nfrom pathlib import Path\n\nfrom {p.package}.catalog.index import OPERATIONS\n\n"
        'SPEC = Path(__file__).resolve().parents[1] / "project-spec.toml"\n\n\n'
        "def test_every_catalog_operation_is_declared_in_the_spec():\n"
        '    nouns = tomllib.loads(SPEC.read_text())["nouns"]\n'
        '    declared = {op for noun in nouns for op in noun["operations"]}\n'
        "    assert set(OPERATIONS) <= declared\n",
    }
    out |= _kernel(p) | _catalog(p) | _nouns(p)
    for flow in p.flows:
        out[f"{pkg}/flows/{flow.name}.py"] = _doc(
            f"{flow.purpose.rstrip('.') or flow.name}. Calls {', '.join(flow.uses)} through the catalog."
        )
    for a in p.adapters:
        out[f"{pkg}/adapters/{a.name}.py"] = _doc(
            f"{a.purpose.rstrip('.') or a.name}. Wraps {a.wraps}; implements {a.implements} from kernel.resources."
        )
    for s in p.py_surfaces:
        out[f"{pkg}/surfaces/{s}.py"] = _surface(p, s)
    return out
