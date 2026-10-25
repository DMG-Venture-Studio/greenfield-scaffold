"""prove_checks.py against a toy tree: a clean run exits 0, and a check that fails only on the final clean-tree
re-run is named with its output, so a flaky check is diagnosable from the CI log.
Run: python -m pytest -q test_prove_checks.py   (or: python test_prove_checks.py)"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "plugins" / "greenfield" / "engine" / "toolkit" / "prove_checks.py"
NO_BAD = "import sys\nsys.exit('found bad' if 'bad' in open('target.txt').read() else 0)\n"
# Fails on its third run only: the baseline and the one plant pass it, the final re-run does not.
FLAKY = (
    "import pathlib, sys\n"
    "p = pathlib.Path(sys.argv[1])\n"
    "n = int(p.read_text() or 0) + 1 if p.exists() else 1\n"
    "p.write_text(str(n))\n"
    "sys.exit(f'flaked on run {n}' if n == {fail_on} else 0)\n"
)


def prove(fail_on: int) -> subprocess.CompletedProcess[str]:
    tree, state = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
    (tree / "target.txt").write_text("fine\n")
    (tree / "no_bad.py").write_text(NO_BAD)
    (tree / "flaky.py").write_text(FLAKY.replace("{fail_on}", str(fail_on)))
    py, counter = json.dumps(sys.executable), json.dumps(str(state / "runs"))
    (tree / "plants.toml").write_text(
        f'[[check]]\nname = "no-bad"\nrun = [{py}, "no_bad.py"]\n\n'
        f'[[check]]\nname = "flaky"\nrun = [{py}, "flaky.py", {counter}]\n\n'
        '[[plant]]\nlabel = "a bad line"\nfile = "target.txt"\nappend = "bad\\n"\n'
        'expect = { check = "no-bad", says = "found bad" }\n'
    )
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(tree / "plants.toml")], capture_output=True, text=True, timeout=60, check=False
    )


def test_clean_run_passes():
    result = prove(fail_on=0)
    assert result.returncode == 0, result.stderr
    assert "caught  a bad line" in result.stdout and not result.stderr


def test_unclean_tree_names_the_check_and_its_output():
    result = prove(fail_on=3)
    assert result.returncode == 1
    assert "caught  a bad line" in result.stdout
    assert "the tree did not come back clean after the plants: ['flaky']" in result.stderr
    assert "--- flaky\nflaked on run 3" in result.stderr
    assert "no-bad" not in result.stderr


if __name__ == "__main__":
    test_clean_run_passes()
    print("caught  test_clean_run_passes")
    test_unclean_tree_names_the_check_and_its_output()
    print("caught  test_unclean_tree_names_the_check_and_its_output")
