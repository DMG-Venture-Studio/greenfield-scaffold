# Error Handling

Comprehensive guide to exit codes, error messages, and structured error output.

## Exit Code Standards

### Recommended Semantic Codes

| Code | Name | Meaning | Example |
|------|------|---------|---------|
| 0 | OK | Success | Operation completed |
| 1 | GENERAL | General failure | Catch-all for unspecified errors |
| 2 | USAGE | Usage error | Bad arguments, unknown flags, invalid syntax |
| 3 | NOT_FOUND | Resource not found | File, user, deployment, service doesn't exist |
| 4 | PERMISSION | Permission denied | Auth failure, insufficient rights, expired token |
| 5 | CONFLICT | Conflict | Resource already exists, concurrent modification |
| 75 | TEMPFAIL | Temporary failure | Network timeout, rate limit, service unavailable — retry may help |
| 78 | CONFIG | Configuration error | Missing config file, invalid config value |

### BSD sysexits.h (Extended Reference)

For CLIs that need more granularity:

| Code | Name | Meaning |
|------|------|---------|
| 64 | EX_USAGE | Command used incorrectly |
| 65 | EX_DATAERR | Input data incorrect |
| 66 | EX_NOINPUT | Input file not found or not readable |
| 67 | EX_NOUSER | Addressee/user unknown |
| 68 | EX_NOHOST | Host name unknown |
| 69 | EX_UNAVAILABLE | Service unavailable |
| 70 | EX_SOFTWARE | Internal software error |
| 71 | EX_OSERR | System error (fork, pipe, etc.) |
| 72 | EX_OSFILE | Critical OS file missing |
| 73 | EX_CANTCREAT | Can't create output file |
| 74 | EX_IOERR | I/O error on file operation |
| 75 | EX_TEMPFAIL | Temporary failure — retry later |
| 76 | EX_PROTOCOL | Remote protocol error |
| 77 | EX_NOPERM | Permission denied |
| 78 | EX_CONFIG | Configuration error |

### Signal Exit Codes

When a process is killed by a signal, the exit code is `128 + signal_number`:

| Code | Signal | Meaning |
|------|--------|---------|
| 130 | SIGINT (2) | User pressed Ctrl-C |
| 137 | SIGKILL (9) | Process killed forcefully |
| 141 | SIGPIPE (13) | Broken pipe (reader closed) |
| 143 | SIGTERM (15) | Process terminated gracefully |

### Exit Code Rules

1. **Document your exit codes** in `--help` or a man page
2. **Be consistent** — same error type always returns the same code
3. **Distinguish transient from permanent** — code 75 means "retry might work"
4. **Never use exit codes above 125** for application errors (reserved for signals and shells)
5. **Exit immediately on SIGPIPE** (code 141) — don't treat broken pipe as an error

## Structured Error Format

### Error Envelope

When `--json` is active, errors must be machine-parseable:

```json
{
  "status": "error",
  "error": {
    "code": "AUTH_EXPIRED",
    "message": "API token expired on 2026-03-01. Authentication required.",
    "fix": "Run: mycli auth login --refresh",
    "transient": false,
    "details": {
      "token_expired_at": "2026-03-01T00:00:00Z",
      "auth_provider": "oauth2"
    }
  }
}
```

### Error Fields

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `code` | string | Yes | Machine-readable error identifier (SCREAMING_SNAKE_CASE) |
| `message` | string | Yes | Human-readable description |
| `fix` | string | Yes | Actionable fix — ideally a runnable command |
| `transient` | boolean | Yes | Whether retrying might succeed |
| `details` | object | No | Additional context (key-value pairs relevant to the error) |

### Error Code Taxonomy

Organize error codes by domain:

```
AUTH_EXPIRED        — Authentication token expired
AUTH_INVALID        — Invalid credentials
AUTH_MISSING        — No credentials provided

RESOURCE_NOT_FOUND  — Requested resource doesn't exist
RESOURCE_CONFLICT   — Resource already exists
RESOURCE_LOCKED     — Resource is locked by another operation

NETWORK_TIMEOUT     — Connection timed out (transient)
NETWORK_DNS         — DNS resolution failed
NETWORK_REFUSED     — Connection refused

CONFIG_MISSING      — Configuration file not found
CONFIG_INVALID      — Configuration file has invalid syntax
CONFIG_FIELD        — Required configuration field missing

INPUT_INVALID       — Input validation failed
INPUT_TOO_LARGE     — Input exceeds size limits
INPUT_FORMAT        — Input format not recognized

QUOTA_EXCEEDED      — Usage quota exceeded
RATE_LIMITED        — Too many requests (transient)
```

## Human-Readable Error Messages

### The Four Components

Every error message should contain:

```
Error: Cannot deploy to production — deployment 'web-app' has failing health checks.

  3 of 5 pods are in CrashLoopBackOff state.

Fix: Check pod logs with: mycli logs web-app --failing
     Or force deploy with: mycli deploy --env production --force

Docs: https://docs.example.com/troubleshooting/health-checks
```

1. **What**: "Cannot deploy to production"
2. **Context**: "deployment 'web-app' has failing health checks, 3 of 5 pods"
3. **Fix**: Exact commands to resolve or bypass
4. **Reference**: Link to relevant documentation

### Error Message Rules

1. **Rewrite technical errors into human language**: Turn `EACCES: permission denied, open '/etc/config'` into `Cannot write to /etc/config — permission denied. Try: sudo mycli config set ...`
2. **Include the failing input**: If a flag value was invalid, echo it back: `Invalid environment 'prod-us'. Valid values: staging, production`
3. **Suggest the closest match**: For typos, suggest corrections: `Unknown command 'deplooy'. Did you mean 'deploy'?`
4. **Use stderr for all error output**: Never mix error messages with data on stdout
5. **Prefix with program name**: `mycli: error: ...` helps identify which tool failed in a pipeline

### Warning Messages

Warnings go to stderr and should not prevent the command from completing:

```
mycli: warning: Config file at ~/.mycli.yaml uses deprecated format. Run: mycli config migrate
```

For `--json` mode, include warnings in the envelope:

```json
{
  "status": "ok",
  "data": { ... },
  "warnings": [
    {
      "code": "CONFIG_DEPRECATED",
      "message": "Config file uses deprecated format",
      "fix": "Run: mycli config migrate"
    }
  ]
}
```

## Signal Handling

### SIGINT (Ctrl-C)

1. Print a brief acknowledgment to stderr: `\nInterrupted. Cleaning up...`
2. Clean up resources (temp files, partial writes, lock files)
3. Add a timeout to cleanup (5 seconds max)
4. Allow a second Ctrl-C to skip cleanup and exit immediately
5. Exit with code 130

### SIGTERM

1. Begin graceful shutdown
2. Clean up resources
3. Exit with code 143

### SIGPIPE

1. Exit immediately and silently with code 141
2. Do NOT treat broken pipe as an error
3. Do NOT print an error message
4. This happens when piping to `head` or when the reader closes — it's normal

### Crash-Only Design

Programs should tolerate being started without prior cleanup:
- Check for stale lock files and clean them up on start
- Use atomic writes (write to temp file, then rename) to prevent corruption
- Don't assume previous invocations completed successfully
