"""Mirror a harness audit report into GitHub issues with the gh CLI.

One rollup issue whose comments are the dated review log, and one issue per finding at or above a severity,
deduplicated by the finding's id and closed when the finding disappears. Standard library only.

Usage: python harness_issues.py report.json [--findings auditor.json] [--min-severity high] [--max-new 5]
       [--dry-run]

The rollup issue's body carries the latest metrics as a JSON comment, so the next run can use it as a
baseline when no earlier report artifact exists (python harness_issues.py --baseline-out last.json).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

LABEL, ROLLUP_LABEL = "harness", "harness-audit"
ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
MARK = re.compile(r"<!-- harness-finding: ([0-9a-f]{10}) -->")
METRICS_MARK = re.compile(r"<!-- harness-metrics: (\{.*?\}) -->", re.DOTALL)
# gh subcommands that change the repository, and so are only printed in a dry run.
WRITES = ("create", "edit", "close", "comment")


def gh(*args: str, stdin: str | None = None, dry: bool = False) -> str:
    """The stdout of a gh command; a dry run prints writes instead of running them."""
    if dry and args[0] in {"issue", "label"} and args[1] in WRITES:
        print("DRY", "gh", *args[:4], file=sys.stderr)
        return ""
    done = subprocess.run(["gh", *args], input=stdin or "", capture_output=True, text=True, check=False)
    if done.returncode:
        raise SystemExit(f"gh {' '.join(args[:3])} failed: {done.stderr.strip()}")
    return done.stdout


def open_issues(label: str) -> list[dict]:
    """The open issues carrying a label, with their number, title and body."""
    out = gh(
        "issue", "list", "--label", label, "--state", "open", "--limit", "200", "--json", "number,title,body"
    )
    return json.loads(out or "[]")


def ensure_labels(*, dry: bool) -> None:
    """Create the finding and rollup labels when the repository lacks them."""
    labels = json.loads(gh("label", "list", "--json", "name", "--limit", "200") or "[]")
    existing = {x["name"] for x in labels}
    for name, color in ((LABEL, "5319e7"), (ROLLUP_LABEL, "0e8a16")):
        if name not in existing:
            gh("label", "create", name, "--color", color, dry=dry)


def finding_body(f: dict, head: str) -> str:
    """An issue body for one finding: evidence, why it matters, a fix prompt, and the id marker."""
    evidence = "\n".join(f"- {e}" for e in f.get("evidence", [])[:12]) or "- (see the report)"
    fix = f.get("fix_prompt") or (
        f"In this repository, resolve harness finding {f['id']} ({f['lens']}): {f['message']}. "
        "Change only the files the evidence names, run the project's checks, and confirm the finding is "
        "gone with `python tools/toolkit/harness_audit.py --md /dev/stdout`."
    )
    why = f.get("why") or "It costs context or time on every session, or tells the agent something untrue."
    return (
        f"**{f['severity']}** [{f['lens']}] {f['message']}\n\n**Evidence**\n{evidence}\n\n"
        f"**Why it matters**\n{why}\n\n"
        f"**Fix prompt** (paste into a coding session)\n\n```\n{fix}\n```\n\nFirst seen at `{head}`.\n\n"
        f"<!-- harness-finding: {f['id']} -->"
    )


def _tracked_issues() -> dict[str, int]:
    """The open finding issues, keyed by the finding id their body marks."""
    tracked = {}
    for issue in open_issues(LABEL):
        m = MARK.search(issue["body"] or "")
        if m:
            tracked[m.group(1)] = issue["number"]
    return tracked


def sync(report: dict, extra: list[dict], min_sev: str, max_new: int, *, dry: bool) -> dict:
    """Close issues for resolved findings and open up to max_new for findings at or above min_sev."""
    ensure_labels(dry=dry)
    findings = [f for f in report["findings"] + extra if ORDER[f["severity"]] <= ORDER[min_sev]]
    current = {f["id"]: f for f in findings}
    tracked = _tracked_issues()
    created = closed = 0
    for fid, number in tracked.items():
        if fid not in current:
            resolved = f"Resolved: not reported at `{report['head']}`."
            gh("issue", "comment", str(number), "--body", resolved, dry=dry)
            gh("issue", "close", str(number), dry=dry)
            closed += 1
    for f in sorted(findings, key=lambda f: ORDER[f["severity"]]):
        if f["id"] in tracked or created >= max_new:
            continue
        title = f"[harness] {f['message'][:110]}"
        gh(
            "issue",
            "create",
            "--label",
            LABEL,
            "--title",
            title,
            "--body-file",
            "-",
            stdin=finding_body(f, report["head"]),
            dry=dry,
        )
        created += 1
    return {"created": created, "closed": closed, "open_before": len(tracked), "eligible": len(findings)}


def rollup(report: dict, markdown: str, outcome: dict, *, dry: bool) -> None:
    """Rewrite the rollup issue's body with the latest report and log this run as a comment on it."""
    metrics = json.dumps(
        {
            "head": report["head"],
            "metrics": report["metrics"],
            "findings": [{"id": f["id"]} for f in report["findings"]],
        }
    )
    body = (
        "Weekly harness audit. The latest report is below; each comment is one week's entry."
        f"\n\n{markdown}\n\n<!-- harness-metrics: {metrics} -->"
    )
    issues = open_issues(ROLLUP_LABEL)
    entry = (
        f"Audit at `{report['head']}` ({report['generated']}): {len(report['findings'])} findings; "
        f"issues created {outcome['created']}, closed {outcome['closed']}.\n\n"
        + "\n".join(f"- {k}: {v}" for k, v in report["metrics"].items())
    )
    if issues:
        number = str(issues[0]["number"])
        gh("issue", "edit", number, "--body-file", "-", stdin=body, dry=dry)
        gh("issue", "comment", number, "--body-file", "-", stdin=entry, dry=dry)
    else:
        gh(
            "issue",
            "create",
            "--label",
            ROLLUP_LABEL,
            "--title",
            "Harness audit",
            "--body-file",
            "-",
            stdin=body,
            dry=dry,
        )


def baseline_from_rollup(out: Path) -> bool:
    """Write the metrics stored in the rollup issue to a file; False when there are none."""
    for issue in open_issues(ROLLUP_LABEL):
        m = METRICS_MARK.search(issue["body"] or "")
        if m:
            out.write_text(m.group(1))
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    """Sync the report's findings and rollup to GitHub issues, or write the stored baseline."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("report", type=Path, nargs="?")
    ap.add_argument("--markdown", type=Path, help="the report's markdown, for the rollup body")
    ap.add_argument("--findings", type=Path, help="the auditor's findings JSON (a list), merged in")
    ap.add_argument("--min-severity", default="high", choices=list(ORDER))
    ap.add_argument("--max-new", type=int, default=5)
    ap.add_argument("--baseline-out", type=Path, help="write the rollup's stored metrics here and exit")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if args.baseline_out:
        return 0 if baseline_from_rollup(args.baseline_out) else 1
    report = json.loads(args.report.read_text())
    extra = json.loads(args.findings.read_text()) if args.findings and args.findings.exists() else []
    outcome = sync(report, extra, args.min_severity, args.max_new, dry=args.dry_run)
    markdown = args.markdown.read_text() if args.markdown else ""
    rollup(report, markdown[:60000], outcome, dry=args.dry_run)
    print(json.dumps(outcome))
    return 0


if __name__ == "__main__":
    sys.exit(main())
