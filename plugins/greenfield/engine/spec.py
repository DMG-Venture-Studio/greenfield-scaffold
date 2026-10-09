"""Write project-spec.toml: the architecture the contracts are rendered from, and nothing else."""

from __future__ import annotations

import json

from intake import PY_SURFACES, Project


def _s(value: str) -> str:
    return json.dumps(value)


def _a(values: tuple[str, ...] | list[str]) -> str:
    return json.dumps(list(values))


HEADER = """\
# The architecture of this project, declared once. The import contracts are rendered from this file
# (`tools/toolkit/render_import_contracts.py`), so the only way to allow an import is to change it here.
# Every change is a reviewed decision: a decision record, the contracts re-rendered, then the code.
"""


def render(p: Project) -> str:
    """The spec file as TOML."""
    out = [
        HEADER,
        "[project]",
        f"name = {_s(p.name)}",
        f"package = {_s(p.package)}",
        f"python = {_s(p.python)}",
        f"database = {_s(p.database)}",
        f"first_operation = {_s(p.first_operation)}",
        "",
        "[surfaces]",
    ]
    out += [f"{s} = {'true' if s in p.surfaces else 'false'}" for s in (*PY_SURFACES, "web")]
    out += ["", "[externals]"]
    if p.driver:
        out.append(f"database_driver = {_s(p.driver)}")
    out.append(f"lazy = {_a(p.lazy)}")
    frameworks = ", ".join(f"{k} = {_s(v)}" for k, v in p.frameworks.items())
    out.append(f"surface_frameworks = {{ {frameworks} }}" if frameworks else "surface_frameworks = {}")
    for n in p.nouns:
        out += [
            "",
            "[[nouns]]",
            f"name = {_s(n.name)}",
            f"purpose = {_s(n.purpose)}",
            f"owns = {_a(n.owns)}",
            f"operations = {_a(n.operations)}",
            f"roles = {_a(n.roles)}",
            f"depends_on = {_a(n.depends_on)}",
        ]
        if p.web:
            out.append(f"screens = {'true' if n.screens else 'false'}")
    for f in p.flows:
        out += ["", "[[flows]]", f"name = {_s(f.name)}", f"purpose = {_s(f.purpose)}", f"uses = {_a(f.uses)}"]
    for a in p.adapters:
        out += [
            "",
            "[[adapters]]",
            f"name = {_s(a.name)}",
            f"wraps = {_s(a.wraps)}",
            f"implements = {_s(a.implements)}",
            f"purpose = {_s(a.purpose)}",
        ]
    out += ["", "[authority]", f"principals = {_a(p.principals)}", f"spend = {_a(p.spend)}", ""]
    return "\n".join(out)
