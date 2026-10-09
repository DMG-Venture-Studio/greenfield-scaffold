# Weekly harness audit (scheduled task or local session)

Use this as the prompt of a weekly scheduled task with the repository attached, or paste it into a local
Claude Code session. A local session also has the session transcripts, so it measures agent and skill use
from real calls instead of commit messages.

---

Run this repository's weekly harness audit. Do not edit tracked files.

1. Collect. Run
   `python3 tools/toolkit/harness_audit.py --since "7 days ago" --json /tmp/harness-report.json --md /tmp/harness-report.md`
   - Add `--baseline <last week's report>` if you can find last week's report: the previous run's artifact, or
     the metrics comment on the open "Harness audit" issue (`python3 tools/toolkit/harness_issues.py --baseline-out /tmp/last.json`).
   - Add `--time-hooks` once a month, or when the hooks or settings changed this week (`git log --since="7 days ago" -- .claude tools/git_hooks`).
   - Running locally, add `--transcripts ~/.claude/projects/<this repo's folder>`.
2. Judge. Run the harness-auditor subagent (.claude/agents/harness-auditor.md) on the report, following its procedure and budget.
3. Deliver, in this order of preference:
   - If a claude.ai Project is attached, write the report plus the auditor's section to
     `harness/audit-<YYYY-MM-DD>.md` in the Project, replacing nothing. If a finding is a cleanup, add a
     paste-ready lane prompt with its own file boundary.
   - If the repository variable or the operator asks for issues, run
     `python3 tools/toolkit/harness_issues.py /tmp/harness-report.json --markdown /tmp/harness-report.md --findings harness-findings.json`.
   - Otherwise, print the report and the auditor's section.
4. Finish with three lines:
   - the session-start bytes and the change since last week
   - the count of new and resolved findings
   - the one thing most worth doing this week
