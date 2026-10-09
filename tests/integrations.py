"""Check the scaffold against the add-ons it hands over to: serial-build's scope, and factory's installer.

    python3 tests/integrations.py --harness <clone of serial-build-harness> --factory <clone of factory>

Proven at serial-build-harness 60454e1 and factory 8af1165. Each fixture with serial_build on is
generated, then the harness's own scripts run on it as /serial-build:scope's "scoped" path would. factory's
installer then runs on the result, and the files it skips must be exactly the two the bootstrap prompt merges.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "plugins" / "greenfield" / "engine" / "scaffold.py"
EXPECTED_FACTORY_SKIPS = {".claude/settings.json", "CLAUDE.md"}


def sh(cmd: list[str], cwd: Path) -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode:
        raise SystemExit(f"FAILED in {cwd}: {' '.join(cmd)}\n{result.stdout}\n{result.stderr}")
    return result.stdout


def check(fixture: Path, harness: Path, factory: Path, base: Path) -> None:
    project = base / fixture.stem
    sh([sys.executable, str(ENGINE), "--intake", str(fixture), "--dest", str(project), "--git"], ROOT)
    sb = harness / "plugins" / "serial-build"
    state = sh(["sh", str(sb / "scripts" / "detect-state.sh")], project).splitlines()[0]
    if state != "state: scoped":
        raise SystemExit(f"{fixture.stem}: detect-state says {state!r}, not scoped")
    sh(["sh", str(sb / "scripts" / "check-config.sh")], project)
    date = json.loads(fixture.read_text())["date"]
    answers = f"docs/decisions/sources/scoping-answers-{date}.json"
    render = ["sh", str(sb / "skills" / "scope" / "scripts" / "render.sh"), "--answers", answers]
    dry = sh([*render, "--config", ".claude/serial-build.json", "--dry-run"], project)
    kept = [line for line in dry.splitlines() if "exists, kept" in line]
    if kept:
        raise SystemExit(f"{fixture.stem}: the harness would leave scaffold files it needs to change:\n{kept}")
    sh([*render, "--config", ".claude/serial-build.json"], project)
    canon = sh(["sh", str(sb / "scripts" / "check-canon.sh")], project)
    gate = subprocess.run(
        [sys.executable, "tools/toolkit/harness_audit.py", "--gate"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    if gate.returncode:
        raise SystemExit(f"{fixture.stem}: the harness gate fails once serial-build's files are in:\n{gate.stderr}")
    settings = json.loads((project / ".claude" / "settings.json").read_text())
    if "worktree" not in settings or ("enabledPlugins" not in settings):
        raise SystemExit(f"{fixture.stem}: the settings merge lost a block: {sorted(settings)}")
    sh(["git", "add", "-A"], project)
    sh(["git", "commit", "-q", "-m", "scope"], project)
    install = sh(["bash", str(factory / "install.sh"), "--dry-run", "."], project)
    skipped = {line.split()[1] for line in install.splitlines() if line.strip().startswith("skip ")}
    if skipped != EXPECTED_FACTORY_SKIPS:
        raise SystemExit(f"{fixture.stem}: factory skips {sorted(skipped)}, the prompt merges {EXPECTED_FACTORY_SKIPS}")
    passes = sum(line.startswith("PASS") for line in canon.splitlines())
    print(
        f"== {fixture.stem}: scoped, config ok, rendered with nothing kept, canon {passes} PASS, "
        f"harness gate passes, factory skips exactly {sorted(skipped)}"
    )


def main(argv: list[str]) -> int:
    harness = Path(argv[argv.index("--harness") + 1]).resolve()
    factory = Path(argv[argv.index("--factory") + 1]).resolve()
    fixtures = [
        f
        for f in sorted((ROOT / "tests" / "fixtures").glob("*.json"))
        if json.loads(f.read_text()).get("addons", {}).get("serial_build")
    ]
    with tempfile.TemporaryDirectory() as tmp:
        for fixture in fixtures:
            check(fixture, harness, factory, Path(tmp))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
