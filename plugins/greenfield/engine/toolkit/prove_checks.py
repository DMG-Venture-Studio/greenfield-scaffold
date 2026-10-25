"""Prove every check still refuses what it exists to refuse.

Each plant in the plants file is one violation: a line appended to a file or a file created. The runner
checks the clean tree passes every check, applies one plant, runs the checks, requires the named check to
fail with the expected text, and restores the tree before the next plant, even when a check crashes. Run it
in CI on a schedule: a check that stops failing on its plant has been switched off, whoever did it.
"""

import os
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

type Table = dict[str, object]


def _strs(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _env(check: Table) -> dict[str, str]:
    extra = check.get("env", {})
    return {**os.environ, **({str(k): str(v) for k, v in extra.items()} if isinstance(extra, dict) else {})}


def _run_one(root: Path, check: Table) -> str | None:
    """Run one check; return its output when it fails, None when it passes. A failed preparation fails it."""
    env = _env(check)
    prepare = check.get("prepare", [])
    for step in [*(prepare if isinstance(prepare, list) else []), check["run"]]:
        result = subprocess.run(_strs(step), cwd=root, env=env, capture_output=True, text=True, check=False)
        if result.returncode:
            return result.stdout + result.stderr
    return None


def _run_checks(root: Path, checks: list[Table]) -> dict[str, str]:
    """Run every check; return the output of each one that failed, by name."""
    outputs = {str(check["name"]): _run_one(root, check) for check in checks}
    return {name: output for name, output in outputs.items() if output is not None}


def _edits(plant: Table) -> list[Table]:
    """The plant's edits: its own file, and any further ones it lists under edits."""
    extra = plant.get("edits", [])
    rows = [row for row in extra if isinstance(row, dict)] if isinstance(extra, list) else []
    return ([plant] if "file" in plant else []) + rows


@contextmanager
def _planted(root: Path, plant: Table) -> Iterator[None]:
    """Apply one plant for the duration of the block, then put the tree back exactly."""
    saved: list[tuple[Path, str | None]] = []
    made: list[Path] = []  # folders the plant created; everything in them appeared during the plant
    try:
        for edit in _edits(plant):
            path = root / str(edit["file"])
            saved.append((path, path.read_text() if path.exists() else None))
            missing = [
                d for d in [path.parent, *path.parent.parents] if d.is_relative_to(root) and not d.exists()
            ]
            made += reversed(missing)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text((saved[-1][1] or "") + str(edit.get("append", edit.get("create", ""))))
        yield
    finally:
        for path, before in reversed(saved):
            if before is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(before)
        for folder in reversed(made):
            shutil.rmtree(folder, ignore_errors=True)


def _verdict(plant: Table, failed: dict[str, str]) -> str | None:
    """Why the plant was not caught as expected, or None when it was."""
    expect = plant.get("expect")
    if not isinstance(expect, dict):
        return "the plant has no expect table"
    output = failed.get(str(expect["check"]))
    if output is None:
        return f"{expect['check']} passed"
    if str(expect["says"]) not in output:
        return f"{expect['check']} failed without saying {expect['says']!r}"
    return None


def main(argv: list[str]) -> int:
    """Run the plants file given on the command line against the tree that holds it."""
    plants_file = Path(argv[0]).resolve()
    root = plants_file.parent
    spec = tomllib.loads(plants_file.read_text())
    checks, plants = spec["check"], spec["plant"]
    baseline = _run_checks(root, checks)
    if baseline:
        detail = "".join(f"--- {name}\n{output}\n" for name, output in baseline.items())
        sys.stderr.write(f"the clean tree fails {sorted(baseline)}; fix it before proving checks\n{detail}")
        return 1
    problems = []
    for plant in plants:
        with _planted(root, plant):
            reason = _verdict(plant, _run_checks(root, checks))
        print(f"{'caught' if reason is None else 'MISSED'}  {plant['label']}")
        if reason:
            problems.append(f"{plant['label']}: {reason}")
    if after := _run_checks(root, checks):
        detail = "".join(f"--- {name}\n{output}\n" for name, output in after.items())
        problems.append(f"the tree did not come back clean after the plants: {sorted(after)}\n{detail}")
    sys.stderr.write("".join(f"{p}\n" for p in problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
