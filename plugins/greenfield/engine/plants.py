"""The plants: one violation per starter check, each with the check that must refuse it and what it says."""

from __future__ import annotations

import json

from intake import Project
from kits import ALWAYS_LOADED_BUDGET

BLOAT = ALWAYS_LOADED_BUDGET // len("Every word here loads. ") + 1  # one rule alone breaks the budget

HEAD = """\
# The planted violations for the Python side: one per rule that matters, each with the check that must
# refuse it and words its refusal must contain. Run from the repository root:
#   uv run python tools/toolkit/prove_checks.py plants.toml
# Every check added later gets its plant here before anything relies on it.
"""


def _plant(label: str, edits: list[tuple[str, str, str]], check: str, says: str) -> str:
    """One [[plant]] table; edits are (file, append|create, text)."""
    lines = ["[[plant]]", f"label = {json.dumps(label)}"]
    if len(edits) == 1:
        path, how, text = edits[0]
        lines += [f"file = {json.dumps(path)}", f"{how} = {json.dumps(text)}"]
    else:
        rows = ",\n".join(f"  {{ file = {json.dumps(f)}, {h} = {json.dumps(t)} }}" for f, h, t in edits)
        lines.append(f"edits = [\n{rows},\n]")
    lines.append(f"expect = {{ check = {json.dumps(check)}, says = {json.dumps(says)} }}")
    return "\n".join(lines) + "\n"


def _checks(p: Project) -> str:
    pkg = p.package
    render = [
        "uv",
        "run",
        "python",
        "tools/toolkit/render_import_contracts.py",
        "--check",
        "project-spec.toml",
        "contracts.toml",
        f"src/{pkg}",
    ]
    return f"""
[[check]]
name = "contracts"
prepare = [{json.dumps(render)}]
run = ["uv", "run", "lint-imports", "--config", "contracts.toml", "--no-cache"]
env = {{ PYTHONPATH = "src" }}

[[check]]
name = "ruff"
run = ["uv", "run", "ruff", "check", "."]

[[check]]
name = "format"
run = ["uv", "run", "ruff", "format", "--check", "."]

[[check]]
name = "types"
run = ["uv", "run", "pyrefly", "check"]

[[check]]
name = "deps"
run = ["uv", "run", "deptry", "src"]

[[check]]
name = "harness"
run = ["uv", "run", "python", "tools/toolkit/harness_audit.py", "--gate"]

[[check]]
name = "tests"
run = ["uv", "run", "pytest", "-q"]
"""


def _contract_plants(p: Project) -> list[str]:
    pkg, first = p.package, p.first_noun
    src = f"src/{pkg}"
    model = f"{src}/{first.name}/model.py"
    out = [
        _plant(
            "a role imports a role above it",
            [(model, "append", f"from {pkg}.{first.name} import ops\n")],
            "contracts",
            "Roles",
        ),
        _plant(
            "a module name outside the role vocabulary",
            [(f"{src}/{first.name}/helpers.py", "create", '"""Helpers."""\n')],
            "contracts",
            "not listed as layers",
        ),
        _plant(
            "a new top-level module", [(f"{src}/utils.py", "create", '"""Utils."""\n')], "contracts", f"{pkg}.utils"
        ),
        _plant(
            "a package the spec does not declare",
            [(f"{src}/undeclared/__init__.py", "create", '"""Undeclared."""\n')],
            "contracts",
            f"{pkg}.undeclared",
        ),
        _plant(
            "a flow or boot reaches a noun's ops without the catalog",
            [(f"{src}/boot.py", "append", f"from {pkg}.{first.name} import ops\n")],
            "contracts",
            "Above the nouns",
        ),
        _plant(
            "the kernel imports a surface",
            [(f"{src}/kernel/envelope.py", "append", f"from {pkg}.surfaces import {p.py_surfaces[0]}\n")],
            "contracts",
            "Ways in are leaves",
        ),
        _plant(
            "the kernel imports a noun",
            [(f"{src}/kernel/errors.py", "append", f"from {pkg}.{first.name} import model\n")],
            "contracts",
            "Tiers",
        ),
        _plant("test tooling in the runtime", [(model, "append", "import pytest\n")], "contracts", "Test tooling"),
        _plant(
            "an import ring inside the kernel",
            [
                (f"{src}/kernel/errors.py", "append", f"from {pkg}.kernel import envelope\n"),
                (f"{src}/kernel/envelope.py", "append", f"from {pkg}.kernel import errors\n"),
            ],
            "contracts",
            "No cycles",
        ),
    ]
    outside = [p.driver] if p.driver else []
    outside += [a.wraps for a in p.adapters] + list(p.frameworks.values())
    if outside:
        out.append(
            _plant(
                "an outside package imported where the spec gives it no home, contracts not re-rendered",
                [(model, "append", f"import {outside[0]}\n")],
                "contracts",
                "is not the render of",
            )
        )
    out += _pair_plants(p)
    if len(p.py_surfaces) > 1:
        a, b = p.py_surfaces[:2]
        out.append(
            _plant(
                "one surface imports another",
                [(f"{src}/surfaces/{b}.py", "append", f"from {pkg}.surfaces import {a}\n")],
                "contracts",
                "Surfaces never import",
            )
        )
    if p.adapters:
        ad = p.adapters[0].name
        out.append(
            _plant(
                "a noun imports an adapter instead of asking for a resource",
                [(model, "append", f"from {pkg}.adapters import {ad}\n")],
                "contracts",
                "Tiers",
            )
        )
        out.append(
            _plant(
                "an adapter imports a noun",
                [(f"{src}/adapters/{ad}.py", "append", f"from {pkg}.{first.name} import model\n")],
                "contracts",
                "Tiers",
            )
        )
    if p.flows:
        fl = p.flows[0].name
        out.append(
            _plant(
                "a flow calls a noun's ops directly",
                [(f"{src}/flows/{fl}.py", "append", f"from {pkg}.{first.name} import ops\n")],
                "contracts",
                "Above the nouns",
            )
        )
    return out


def _pair_plants(p: Project) -> list[str]:
    """Noun to noun: one pair the spec does not connect, and a dependency reached below ops and model."""
    pkg, out = p.package, []
    pair = next(((a, b) for a in p.nouns for b in p.nouns if a is not b and b.name not in a.depends_on), None)
    if pair:
        a, b = pair
        out.append(
            _plant(
                "a noun imports a noun the spec does not let it depend on",
                [(f"src/{pkg}/{a.name}/model.py", "append", f"from {pkg}.{b.name} import model\n")],
                "contracts",
                "Tiers",
            )
        )
    deep = next(
        ((a, d) for a in p.nouns for d in a.depends_on if {"store", "rules", "render"} & set(p.noun(d).roles)), None
    )
    if deep:
        a, d = deep
        role = next(r for r in ("store", "rules", "render") if r in p.noun(d).roles)
        out.append(
            _plant(
                "a noun reaches below its dependency's ops and model",
                [(f"src/{pkg}/{a.name}/ops.py", "append", f"from {pkg}.{d} import {role}\n")],
                "contracts",
                "Tiers",
            )
        )
    return out


def _code_plants(p: Project) -> list[str]:
    target = f"src/{p.package}/{p.first_noun.name}/model.py"
    return [
        _plant(
            "every exception swallowed",
            [
                (
                    target,
                    "append",
                    '\n\ndef swallow() -> None:\n    """Swallow."""\n    try:\n        int("x")\n'
                    "    except Exception:\n        pass\n",
                )
            ],
            "ruff",
            "blind-except",
        ),
        _plant(
            "print outside a surface",
            [(target, "append", '\n\ndef shout() -> None:\n    """Shout."""\n    print(1)\n')],
            "ruff",
            "print",
        ),
        _plant(
            "an import hidden inside a function",
            [
                (
                    target,
                    "append",
                    '\n\ndef late() -> str:\n    """Late."""\n    import json\n\n    return json.dumps(1)\n',
                )
            ],
            "ruff",
            "import-outside-top-level",
        ),
        _plant("a relative import", [(target, "append", "from . import model\n")], "ruff", "relative-imports"),
        _plant(
            "Any instead of a named type",
            [(target, "append", "\nfrom typing import Any\n\nX: Any = 1\n")],
            "ruff",
            "banned-api",
        ),
        _plant("an unformatted line", [(target, "append", "\nX = {  'a':1 }\n")], "format", "would be reformatted"),
        _plant(
            "a value passed where the type says otherwise",
            [(target, "append", '\n\nWRONG: int = "text"\n')],
            "types",
            "bad-assignment",
        ),
        _plant(
            "an import of a package the project does not declare",
            [(target, "append", "import yaml\n")],
            "deps",
            "DEP001",
        ),
        _plant(
            "an always-loaded rule that blows the context budget",
            [(".claude/rules/planted.md", "create", "# Planted\n\n" + "Every word here loads. " * BLOAT + "\n")],
            "harness",
            "load into every session",
        ),
        _plant(
            "an always-loaded rule that names a file that does not exist",
            [(".claude/rules/planted.md", "create", "# Planted\n\nRead `docs/missing.md` before anything.\n")],
            "harness",
            "path(s) that do not exist",
        ),
        _plant(
            "a failing test",
            [("tests/test_planted.py", "create", "def test_planted():\n    assert 1 == 2\n")],
            "tests",
            "failed",
        ),
    ]


def render(p: Project) -> str:
    """The whole plants file for the Python side."""
    return HEAD + _checks(p) + "\n" + "\n".join(_contract_plants(p) + _code_plants(p))
