"""Render the import contracts from the project spec.

The architecture the spec declares is the one lint-imports holds. Re-run after every spec change and
commit both files together; `--check` is the drift check that refuses a contracts file the spec would not
produce.
"""

import ast
import sys
import tomllib
from pathlib import Path

type Table = dict[str, object]

ROLES = ["(ops)", "(render)", "(rules)", "(store)", "(model)"]
SURFACES = ("cli", "http", "mcp", "jobs", "agent_tools")


def _q(items: list[str]) -> str:
    return "[" + ", ".join(f'"{item}"' for item in items) + "]"


def _contract(name: str, kind: str, **fields: str) -> str:
    body = "".join(f"{key} = {value}\n" for key, value in fields.items())
    return f'[[tool.importlinter.contracts]]\nname = "{name}"\ntype = "{kind}"\n{body}'


def _table(spec: Table, key: str) -> Table:
    value = spec.get(key, {})
    return value if isinstance(value, dict) else {}


def _rows(spec: Table, key: str) -> list[Table]:
    value = spec.get(key, [])
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _depends(noun: Table) -> list[str]:
    value = noun.get("depends_on", [])
    return [str(name) for name in value] if isinstance(value, list) else []


def _tiers(pkg: str, spec: Table) -> str:
    """Every package in one tier order; nouns and adapters on one line, independent of each other."""
    nouns = _rows(spec, "nouns")
    siblings = " | ".join([*(str(n["name"]) for n in nouns), "adapters"])
    layers = ["__main__", "surfaces", "boot", "flows", "catalog", siblings, "kernel"]
    allowed = [f"{pkg}.{n['name']}.ops -> {pkg}.{dep}.ops" for n in nouns for dep in _depends(n)]
    allowed += [f"{pkg}.{n['name']}.** -> {pkg}.{dep}.model" for n in nouns for dep in _depends(n)]
    return _contract(
        "Tiers: each package imports only the tiers below it; nouns and adapters never import each other",
        "layers",
        containers=_q([pkg]),
        exhaustive="true",
        layers=_q(layers),
        ignore_imports=_q(allowed),
        unmatched_ignore_imports_alerting='"none"',  # spec permissions, not debt: an unused one is fine
    )


def _roles(pkg: str, spec: Table) -> str:
    return _contract(
        "Roles: inside a noun, ops over render over rules over store over model, and no other module",
        "layers",
        containers=_q([f"{pkg}.{n['name']}" for n in _rows(spec, "nouns")]),
        exhaustive="true",
        layers=_q(ROLES),
    )


def _above(pkg: str) -> str:
    return _contract(
        "Above the nouns, operations are reached through the catalog and a noun's insides not at all",
        "forbidden",
        source_modules=_q([f"{pkg}.{tier}" for tier in ("flows", "boot", "surfaces")]),
        forbidden_modules=_q([f"{pkg}.*.{role}" for role in ("ops", "render", "rules", "store")]),
        allow_indirect_imports="true",
    )


def _surfaces(pkg: str, spec: Table) -> list[str]:
    declared = _table(spec, "surfaces")
    present = [f"({name})" for name in SURFACES if declared.get(name)]
    leaves = _contract(
        "Ways in are leaves: nothing imports a surface but __main__",
        "protected",
        protected_modules=_q([f"{pkg}.surfaces"]),
        allowed_importers=_q([f"{pkg}.__main__"]),
    )
    apart = _contract(
        "Surfaces never import each other, and no surface exists that the spec does not name",
        "layers",
        containers=_q([f"{pkg}.surfaces"]),
        exhaustive="true",
        layers=_q([" | ".join(present)]),
    )
    return [leaves, apart]


def _only(name: str, package: str, importers: list[str]) -> tuple[str, str]:
    contract = _contract(name, "protected", protected_modules=_q([package]), allowed_importers=_q(importers))
    return package, contract


def _externals(pkg: str, spec: Table) -> list[tuple[str, str]]:
    """Each outside package's one home, as (package, contract) pairs."""
    ext = _table(spec, "externals")
    out: list[tuple[str, str]] = []
    driver = ext.get("database_driver")
    if driver:
        out.append(_only("Only a store imports the database driver", str(driver), [f"{pkg}.*.store"]))
    for adapter in _rows(spec, "adapters"):
        name, wraps = adapter["name"], str(adapter["wraps"])
        out.append(_only(f"Only the {name} adapter imports {wraps}", wraps, [f"{pkg}.adapters.{name}"]))
    frameworks = ext.get("surface_frameworks", {})
    if isinstance(frameworks, dict):
        for surface, lib in frameworks.items():
            importers = [f"{pkg}.surfaces.{surface}"]
            out.append(_only(f"Only the {surface} surface imports {lib}", str(lib), importers))
    return out


def imported_packages(source: Path) -> set[str]:
    """Return the top-level name of every package the code under source imports."""
    names: set[str] = set()
    for path in source.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                names |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                names.add(node.module.split(".")[0])
    return names


def render(spec: Table, source: Path) -> str:
    """Return the whole contracts file.

    lint-imports refuses to protect a package nothing imports, so an outside package's contract appears
    with the first import of it, which the contract then holds to its one place.
    """
    pkg = str(_table(spec, "project")["package"])
    present = imported_packages(source)
    externals = [contract for package, contract in _externals(pkg, spec) if package in present]
    head = f'[tool.importlinter]\nroot_package = "{pkg}"\ninclude_external_packages = true\n'
    tooling = _contract(
        "Test tooling never ships in the runtime",
        "forbidden",
        source_modules=_q([pkg]),
        forbidden_modules=_q(["pytest"]),
    )
    cycles = _contract(
        "No cycles among siblings at any package level",
        "acyclic_siblings",
        ancestors=_q([pkg, f"{pkg}.kernel", f"{pkg}.flows"]),
    )
    parts = [_tiers(pkg, spec), _roles(pkg, spec), _above(pkg), *_surfaces(pkg, spec), *externals]
    return head + "\n" + "\n".join([*parts, tooling, cycles])


def main(argv: list[str]) -> int:
    """Write the contracts file, or with --check fail when the committed one is not the render of the spec."""
    check = "--check" in argv
    spec_path, out_path, source = (Path(a) for a in argv if a != "--check")
    text = render(tomllib.loads(spec_path.read_text()), source)
    if not check:
        out_path.write_text(text)
        return 0
    if out_path.exists() and out_path.read_text() == text:
        return 0
    sys.stderr.write(f"{out_path} is not the render of {spec_path}; re-run without --check\n")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
