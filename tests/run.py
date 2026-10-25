"""Generate every fixture, then prove each generated project passes its own checks and catches every plant.

    python3 tests/run.py [fixture-name ...] [--keep DIR] [--no-web]

Needs uv and, for fixtures with a web surface, npm. Network is needed the first time (PyPI and npm).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "plugins" / "greenfield" / "engine" / "scaffold.py"
FIXTURES = ROOT / "tests" / "fixtures"
REFUSED = ROOT / "tests" / "refused"


def sh(cmd: list[str] | str, cwd: Path, *, ok: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str), capture_output=True, text=True, check=False)
    if ok and result.returncode:
        raise SystemExit(f"FAILED in {cwd}: {cmd}\n{result.stdout}\n{result.stderr}")
    return result


def prove(project: Path, plants: str) -> list[str]:
    result = sh([sys.executable, "tools/toolkit/prove_checks.py", plants], project, ok=False)
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if result.returncode:
        raise SystemExit(f"PLANTS FAILED in {project} ({plants}):\n{result.stdout}\n{result.stderr}")
    return lines


def run_fixture(fixture: Path, base: Path, *, web: bool) -> dict[str, object]:
    project = base / fixture.stem
    sh([sys.executable, str(ENGINE), "--intake", str(fixture), "--dest", str(project), "--git"], ROOT)
    sh("uv sync -q", project)
    spec = tomllib.loads((project / "project-spec.toml").read_text())
    pkg = spec["project"]["package"]
    for cmd in (
        "uv run ruff check . --output-format concise",
        "uv run ruff format --check .",
        "uv run pyrefly check",
        f"uv run python tools/toolkit/render_import_contracts.py --check project-spec.toml contracts.toml src/{pkg}",
        "PYTHONPATH=src uv run lint-imports --config contracts.toml --no-cache",
        "uv run deptry src",
        "uv run pytest -q",
        f"uv run python -m {pkg}",
    ):
        sh(cmd, project)
    for sub in ("zz_a", "zz_b"):  # tests/<noun>/test_<role>.py repeats names across nouns; pytest must cope
        (project / "tests" / sub).mkdir()
        (project / "tests" / sub / "test_same.py").write_text("def test_same():\n    assert True\n")
    sh("uv run pytest -q", project)
    for sub in ("zz_a", "zz_b"):
        shutil.rmtree(project / "tests" / sub)
    audit = json.loads(
        sh(
            [sys.executable, "tools/toolkit/harness_audit.py", "--json", "/dev/stdout", "--md", "/dev/null"], project
        ).stdout
    )
    serious = [f["message"] for f in audit["findings"] if f["severity"] in ("high", "medium")]
    if serious:
        raise SystemExit(f"the harness audit finds the scaffold's own docs wanting in {project}:\n{serious}")
    report: dict[str, object] = {
        "files": len(sh("git ls-files", project).stdout.split()),
        "python plants": prove(project, "plants.toml"),
    }
    if web and spec["surfaces"].get("web"):
        sh("npm install --silent --no-audit --no-fund", project / "web")
        report["web plants"] = prove(project, "web/plants.toml")
    status = sh("git status --porcelain", project).stdout.strip()
    if status and not all(line.endswith(("uv.lock", "package-lock.json")) for line in status.splitlines()):
        raise SystemExit(f"the tree did not come back clean in {project}:\n{status}")
    return report


def main(argv: list[str]) -> int:
    names = [a for a in argv if not a.startswith("--") and not Path(a).is_dir()]
    keep = Path(argv[argv.index("--keep") + 1]) if "--keep" in argv else None
    fixtures = [f for f in sorted(FIXTURES.glob("*.json")) if not names or f.stem in names]
    for kit_test in ("test_harness_audit.py", "test_harness_issues.py", "test_prove_checks.py"):  # the kits' own plants
        out = sh([sys.executable, str(ROOT / "tests" / "toolkit" / kit_test)], ROOT).stdout
        print(f"== toolkit {kit_test}: {out.count('caught')} caught")
    for bad in sorted(REFUSED.glob("*.json")):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "never"
            result = sh([sys.executable, str(ENGINE), "--intake", str(bad), "--dest", str(dest)], ROOT, ok=False)
            expect = json.loads(bad.read_text()).get("_expect", "")
            if result.returncode != 3 or dest.exists() or expect not in result.stderr:
                raise SystemExit(f"{bad.name} was not refused with exit 3 saying {expect!r}:\n{result.stderr}")
            print(f"== refused {bad.stem}: {result.stderr.count(chr(10)) - 1} problems named, nothing written")
    with tempfile.TemporaryDirectory() as tmp:
        brief = Path(tmp) / "bootstrap prompt.md"
        brief.write_text("a user's draft\n")
        args = ["--intake", str(FIXTURES / "tally.json"), "--dest", str(Path(tmp) / "never"), "--doc", str(brief)]
        result = sh([sys.executable, str(ENGINE), *args], ROOT, ok=False)
        if result.returncode != 2 or (Path(tmp) / "never").exists():
            raise SystemExit(f"a brief named like the bootstrap prompt was not refused:\n{result.stderr}")
        print("== refused a brief that would overwrite the bootstrap prompt")
    with tempfile.TemporaryDirectory() as tmp:
        base = keep or Path(tmp)
        base.mkdir(parents=True, exist_ok=True)
        for fixture in fixtures:
            report = run_fixture(fixture, base, web="--no-web" not in argv)
            print(f"== {fixture.stem}: {report['files']} files, every check passes on the scaffold")
            for key in ("python plants", "web plants"):
                if key in report:
                    lines = report[key]
                    print(f"   {key}: {sum(line.startswith('caught') for line in lines)}/{len(lines)} caught")
                    for line in lines:
                        print(f"     {line}")
    print(json.dumps({"fixtures": [f.stem for f in fixtures], "result": "pass"}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
