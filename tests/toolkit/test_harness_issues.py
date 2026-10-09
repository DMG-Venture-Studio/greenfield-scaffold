"""harness_issues.py against a fake gh: a resolved finding's issue closes, an open one is not duplicated, a new one
is created, one below the severity threshold is not, and the rollup issue is created once."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

FAKE_GH = """#!/bin/sh
echo "$*" >> "$FAKEGH_LOG"
case "$1 $2" in
  "label list") echo '[{"name":"harness"}]' ;;
  "issue list")
    case "$*" in
      *harness-audit*) echo '[]' ;;
      *) echo '[{"number":7,"title":"old","body":"<!-- harness-finding: aaaaaaaaaa -->"},
               {"number":8,"title":"kept","body":"<!-- harness-finding: bbbbbbbbbb -->"}]' ;;
    esac ;;
  *) cat >/dev/null ;;
esac
"""
REPORT = {
    "head": "abc1234",
    "generated": "2026-10-08T12:00:00",
    "metrics": {"session_start_bytes": 23406},
    "findings": [
        {
            "id": "bbbbbbbbbb",
            "lens": "context",
            "key": "k1",
            "severity": "high",
            "message": "still open",
            "evidence": [],
        },
        {"id": "cccccccccc", "lens": "truth", "key": "k2", "severity": "high", "message": "new high", "evidence": []},
        {"id": "dddddddddd", "lens": "state", "key": "k3", "severity": "medium", "message": "below", "evidence": []},
    ],
}


def test_issue_sync_closes_resolved_keeps_open_and_creates_new():
    tmp = Path(tempfile.mkdtemp())
    (tmp / "gh").write_text(FAKE_GH)
    (tmp / "gh").chmod(0o755)
    (tmp / "report.json").write_text(json.dumps(REPORT))
    env = dict(os.environ, PATH=f"{tmp}:{os.environ['PATH']}", FAKEGH_LOG=str(tmp / "log"))
    script = Path(__file__).resolve().parents[2] / "plugins" / "greenfield" / "engine" / "toolkit" / "harness_issues.py"
    out = subprocess.run(
        [sys.executable, str(script), str(tmp / "report.json")],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    ).stdout
    calls = (tmp / "log").read_text().splitlines()
    assert json.loads(out) == {"created": 1, "closed": 1, "open_before": 2, "eligible": 2}
    assert "issue close 7" in calls and not any(c.startswith("issue close 8") for c in calls)
    assert sum(c.startswith("issue create --label harness --") for c in calls) == 1
    assert sum("--title Harness audit" in c for c in calls) == 1


if __name__ == "__main__":
    test_issue_sync_closes_resolved_keeps_open_and_creates_new()
    print("caught  test_issue_sync_closes_resolved_keeps_open_and_creates_new")
