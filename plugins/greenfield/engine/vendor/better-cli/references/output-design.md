# Output Design

Deep dive into structured output patterns for CLIs that serve both humans and AI agents.

## The JSON Envelope

Use a consistent envelope for every command. Agents parse it once and handle all commands uniformly.

### Success Response

```json
{
  "status": "ok",
  "data": {
    "id": "abc-123",
    "name": "my-resource",
    "created_at": "2026-03-07T10:30:00Z"
  },
  "warnings": [],
  "metadata": {
    "request_id": "req-456",
    "duration_ms": 142
  }
}
```

### Error Response

```json
{
  "status": "error",
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Deployment 'web-app' not found in environment 'staging'",
    "fix": "Run: mycli deployments list --env staging",
    "transient": false
  }
}
```

### List Response (with pagination)

```json
{
  "status": "ok",
  "data": [
    { "id": "abc-123", "name": "resource-1" },
    { "id": "def-456", "name": "resource-2" }
  ],
  "pagination": {
    "total": 42,
    "page": 1,
    "per_page": 20,
    "next_cursor": "eyJpZCI6IDIwfQ=="
  }
}
```

### Design Rules

1. **`status` is always present**: `"ok"` or `"error"` — agents check this first
2. **`data` contains the payload**: Object for single items, array for lists
3. **`error` only appears on failure**: Contains `code` (machine-readable), `message` (human-readable), `fix` (actionable), `transient` (retry hint)
4. **Consistent field names**: Use `snake_case` everywhere. Never mix `camelCase` and `snake_case`
5. **Timestamps in ISO 8601**: Always UTC, always with timezone: `2026-03-07T10:30:00Z`
6. **IDs are strings**: Even if numeric internally — avoids JSON integer precision issues

## NDJSON (Newline-Delimited JSON) for Streaming

For long-running operations, paginated data, or real-time output, use NDJSON — one JSON object per line:

```
{"type":"progress","percent":25,"message":"Downloading dependencies..."}
{"type":"progress","percent":50,"message":"Building application..."}
{"type":"progress","percent":75,"message":"Running tests..."}
{"type":"result","status":"ok","data":{"build_id":"build-789"}}
```

### When to Use NDJSON

- Log streaming: `mycli logs --follow --json`
- Batch operations: `mycli batch delete --json` (one result per item)
- Long builds: progress events followed by final result
- Large datasets: avoid buffering entire array in memory

### NDJSON Rules

1. Each line is a complete, valid JSON object
2. Lines are separated by `\n` (not `\r\n`)
3. Include a `type` field to distinguish event kinds
4. The final line should be the result/summary
5. Progress events go to stderr unless `--json` explicitly includes them

## Field Selection with `--fields`

Limit output to requested columns — critical for token efficiency:

```bash
# Full output: 50 fields, 2000 tokens
mycli users list --json

# Selected output: 3 fields, 200 tokens
mycli users list --json --fields id,name,email
```

### Implementation Pattern

```
mycli list --fields id,name,status    # Comma-separated
mycli list --json --fields id,name    # Works with --json too
mycli list --fields all               # Explicit "give me everything"
```

When `--fields` is omitted, return a sensible default subset (not everything). Document what the default fields are in `--help`.

## Output Versioning

Treat structured output as a versioned API contract.

### Safe Changes (non-breaking)
- Adding new optional fields to objects
- Adding new enum values (when consumers handle unknown values)
- Adding new warning types

### Breaking Changes (require major version bump)
- Removing or renaming fields
- Changing field types (string to number)
- Changing envelope structure
- Reordering array items that were previously stable

### Versioning Strategies

**Approach 1: CLI version implies output version**
```bash
mycli --version  # v2.3.1 — output schema documented per major version
```

**Approach 2: Explicit format version**
```bash
mycli list --json --format-version 2
```

**Approach 3: Schema introspection**
```bash
mycli schema list  # Outputs JSON Schema for `list` command output
```

## Token-Efficient Output

AI agents pay per token. Every unnecessary byte in stdout costs money and context window.

### Cost Comparison (real benchmark from Sol CLI)

| Format | Tokens | Ratio |
|--------|--------|-------|
| Full JSON (all fields) | 626,572 | 100% |
| JSON with `--fields` | 12,952 | 2% |
| Quiet mode (IDs only) | 1,654 | 0.3% |

### Token Reduction Strategies

1. **`--fields`**: Let consumers select only needed columns
2. **`--quiet` / `-q`**: Output only essential values (one per line)
3. **`--no-headers`**: Skip column headers in table output
4. **Pagination**: Don't dump 10,000 rows by default — use `--limit`
5. **Summary mode**: `mycli test --json --summary` outputs pass/fail counts, not full traces

## Human-Readable Output

Default output (when stdout is a TTY) should be designed for human scanning:

### Table Output (no borders)

```
ID          NAME         STATUS    CREATED
abc-123     web-app      running   2m ago
def-456     api-server   stopped   1h ago
ghi-789     worker       running   3d ago
```

Rules:
- No `+---+` borders (breaks parsing, wastes space)
- Align columns with spaces (not tabs)
- Use relative timestamps ("2m ago") for humans, ISO 8601 for `--json`
- Truncate long values with `...` — support `--no-truncate` to show full values
- Support `--no-headers` for scripts

### Single Resource Output

```
Name:       web-app
ID:         abc-123
Status:     running
Created:    2 minutes ago
URL:        https://web-app.example.com
```

### Success Confirmation

```
Created deployment 'web-app' in environment 'staging'
  ID:   deploy-xyz
  URL:  https://staging.example.com

Next steps:
  View logs:    mycli logs deploy-xyz
  Check status: mycli status deploy-xyz
```

The "Next steps" section is gold for both humans and agents — it tells them exactly what to do next.
