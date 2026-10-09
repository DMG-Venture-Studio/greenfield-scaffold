"""Project skills for the kits the spec calls for: better-cli for a CLI, mcp-surface for MCP, agent-runs for agents."""

from __future__ import annotations

import json
from pathlib import Path

from intake import Project

HERE = Path(__file__).parent
VENDOR = HERE / "vendor" / "better-cli"
NOTICE = """\
better-cli, vendored unmodified from https://github.com/yogin16/better-cli at commit 11bde57, under the
Apache License 2.0 in LICENSE beside this file. It is vendored rather than installed as a plugin because its
marketplace entry fails to install on Claude Code 2.1.294 ("source: Invalid input"); the skill itself loads
fine. Replace this copy with the plugin once the upstream entry is fixed.
"""


AUDIT = HERE / "templates" / "harness-audit"
# Bytes every session loads: CLAUDE.md, its imports, unscoped rules, every skill and agent description. About 5k
# tokens. The window is not the constraint; every always-loaded line competes with the task for attention.
ALWAYS_LOADED_BUDGET = 20000


def harness_audit(p: Project) -> dict[str, str]:
    """The doc and harness hygiene kit: the collector's config, the auditor agent, the weekly run and its CI job."""
    config = (AUDIT / "harness.toml").read_text()
    # Decision sources are verbatim history, free to name files that came and went; a vendored skill is not ours.
    exclude = ["docs/decisions/sources/*"] + ([".claude/skills/better-cli/*"] if "cli" in p.kits else [])
    # The auditor's local review log appears when it runs; serial-build's plan exists only while a gate is in flight.
    phantoms = [".harness/*"] + (["docs/plan.md"] if p.addons["serial_build"] else [])
    terms = [p.owner_name] if p.owner_name else []
    for key, values in (("exclude", exclude), ("phantom_ignore", phantoms), ("terms_ignore", terms)):
        line = next(line for line in config.splitlines() if line.startswith(f"{key} = []"))
        config = config.replace(line, line.replace("[]", json.dumps(values), 1), 1)
    config = config.replace("always_loaded_bytes = 10000 ", f"always_loaded_bytes = {ALWAYS_LOADED_BUDGET} ", 1)
    weekly = (AUDIT / "weekly-harness-audit.md").read_text()
    weekly = weekly.replace("python3 tools/toolkit/", "uv run python tools/toolkit/")
    return {
        "harness.toml": config,
        ".claude/agents/harness-auditor.md": (AUDIT / "harness-auditor.md").read_text(),
        ".github/workflows/harness-audit.yml": (AUDIT / "harness-audit.yml").read_text(),
        "tools/toolkit/weekly-harness-audit.md": weekly,
    }


def files(p: Project) -> dict[str, str]:
    """Every kit file, by path from the project root."""
    out: dict[str, str] = harness_audit(p)
    values = {"{{package}}": p.package, "{{owner}}": p.owner_name or "the owner"}
    if "cli" in p.kits:
        for path in sorted(VENDOR.rglob("*")):
            if path.is_file():
                out[f".claude/skills/better-cli/{path.relative_to(VENDOR)}"] = path.read_text()
        out[".claude/skills/better-cli/NOTICE"] = NOTICE
    for kit, name in (("mcp", "mcp-surface"), ("agents", "agent-runs")):
        if kit in p.kits:
            text = (HERE / "templates" / "skills" / f"{name}.md").read_text()
            for key, value in values.items():
                text = text.replace(key, value)
            out[f".claude/skills/{name}/SKILL.md"] = text
    return out
