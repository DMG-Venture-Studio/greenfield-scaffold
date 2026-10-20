"""Project skills for the kits the spec calls for, and the credentials manifest.

better-cli for a CLI, mcp-surface for MCP, agent-runs for agents, and for declared credentials their
manifest and the credentials skill.
"""

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


MANIFEST_HEAD = """\
# Every credential this project uses: who mints it, where its value lives, how long it may live. Values
# never appear here or anywhere in the repository; they live in Infisical and the deployed services.
# A new adapter that needs a key gets its row here in the same change. Checked by
# `uv run python tools/toolkit/credentials.py check`; minting and rotation: the credentials skill.
"""


def _toml(value: object) -> str:
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k} = {_toml(v)}" for k, v in value.items()) + " }" if value else "{}"
    return json.dumps(value)


def manifest(p: Project) -> str:
    """credentials.toml, rendered from the intake's secrets block."""
    manager, rows = p.secrets.get("manager"), p.secrets.get("credentials")
    if not isinstance(manager, dict) or not isinstance(rows, list):
        raise TypeError("the intake shapes secrets as a manager table and a credentials list")
    out = [MANIFEST_HEAD, "[manager]"]
    notes = {
        "host": "  # the Infisical URL, for example https://secrets.example.com",
        "project_id": "  # the Infisical project's ID, from its settings page",
        "rotate_days": "  # 0: rotate on events (a leak, someone leaving), not a calendar",
    }
    out += [f"{k} = {_toml(v)}{notes.get(k, '') if not v or k == 'rotate_days' else ''}" for k, v in manager.items()]
    for row in rows:
        out += ["", "[[credentials]]", row_toml(row).rstrip("\n")]
    return "\n".join(out) + "\n"


def row_toml(row: object) -> str:
    """One credential's keys as TOML lines, in a fixed order."""
    order = ("name", "vendor", "adapter", "path", "envs", "purpose", "keys_page", "rotate_days")
    table = row if isinstance(row, dict) else {}
    return "".join(f"{k} = {_toml(table[k])}\n" for k in order if k in table)


def files(p: Project) -> dict[str, str]:
    """Every kit file, by path from the project root."""
    out: dict[str, str] = harness_audit(p)
    values = {"{{package}}": p.package, "{{owner}}": p.owner_name or "the owner", "{{slug}}": p.slug}
    if "cli" in p.kits:
        for path in sorted(VENDOR.rglob("*")):
            if path.is_file():
                out[f".claude/skills/better-cli/{path.relative_to(VENDOR)}"] = path.read_text()
        out[".claude/skills/better-cli/NOTICE"] = NOTICE
    if "credentials" in p.kits:
        out["credentials.toml"] = manifest(p)
    for kit, name in (("mcp", "mcp-surface"), ("agents", "agent-runs"), ("credentials", "credentials")):
        if kit in p.kits:
            text = (HERE / "templates" / "skills" / f"{name}.md").read_text()
            for key, value in values.items():
                text = text.replace(key, value)
            out[f".claude/skills/{name}/SKILL.md"] = text
    return out
