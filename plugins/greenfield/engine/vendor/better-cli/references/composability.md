# Composability

Unix philosophy in modern CLIs — designing for pipes, chains, and agent workflows.

## Core Principle

> Make each program do one thing well. To do a new job, build afresh rather than complicate old programs by adding new features. Expect the output of every program to become the input to another, as yet unknown, program. — Doug McIlroy

## The Three Streams

```
stdin   →  Your CLI  →  stdout (data)
                     →  stderr (diagnostics)
```

- **stdin**: Accept input from pipes or files
- **stdout**: Primary output data — clean, parseable, no noise
- **stderr**: Everything else — errors, warnings, progress, debug info

## Pipe-Friendly Output

### Do

```bash
# Clean output that pipes well
mycli users list --fields id,email
# abc-123  alice@example.com
# def-456  bob@example.com

# JSON for structured consumption
mycli users list --json --fields id,email | jq '.[].email'

# Quiet mode for IDs only
mycli users list -q
# abc-123
# def-456
```

### Don't

```bash
# Table borders break parsing
mycli users list
# +--------+-------------------+
# | ID     | Email             |
# +--------+-------------------+
# | abc-123| alice@example.com |
# +--------+-------------------+

# Colors in pipes waste tokens and break jq
mycli users list | jq .
# parse error: Invalid string at line 1, column 5
# (because of ANSI escape codes)
```

## stdin Patterns

### Reading from stdin

Support the `-` convention (POSIX standard) or `--stdin` flag:

```bash
# Pipe input
echo "abc-123" | mycli delete --stdin
cat ids.txt | mycli delete --stdin

# POSIX dash convention
mycli process -f -

# Explicit flag
mycli deploy --config-stdin < config.yaml
```

### Implementation Pattern

```
If --stdin flag is set OR stdin is not a TTY and no file argument given:
  Read from stdin
Else:
  Read from file argument or use defaults
```

### Rules

1. Auto-detect stdin when it's not a TTY — but document this behavior
2. Support `--stdin` as an explicit flag (clearer for scripts)
3. Never prompt when reading from stdin — the user is piping data, not typing
4. Handle empty stdin gracefully (not with a hang or cryptic error)

## Cross-Command Chaining

Design commands so their output feeds naturally into other commands.

### Pattern: Create-Then-Use

```bash
# Create outputs the ID
ID=$(mycli create --name web-app --json | jq -r '.data.id')

# Subsequent commands use the ID
mycli deploy --id "$ID" --env staging
mycli status --id "$ID"
mycli logs --id "$ID" --follow
```

For this to work:
1. Create commands MUST output the created resource's identifier
2. IDs must be in a predictable location in JSON output
3. `--quiet` mode should output just the ID: `mycli create -q` → `abc-123`

### Pattern: List-Filter-Act

```bash
# List → Filter → Act pipeline
mycli pods list --json --fields name,status \
  | jq -r '.data[] | select(.status == "failed") | .name' \
  | xargs -I {} mycli pods restart --name {}
```

For this to work:
1. List commands support `--json` and `--fields`
2. Action commands accept resource identifiers as flags
3. Output is clean (no ANSI codes contaminating the pipe)

### Pattern: Dry-Run-Then-Apply

```bash
# Preview changes
mycli deploy --env production --dry-run --json > plan.json

# Review (human or agent)
cat plan.json | jq '.changes[] | "\(.action) \(.resource)"'

# Apply the same operation
mycli deploy --env production --yes
```

## NDJSON for Streaming

Use Newline-Delimited JSON for operations that produce results over time:

```bash
mycli logs --follow --json
# {"timestamp":"2026-03-07T10:30:00Z","level":"info","message":"Request received"}
# {"timestamp":"2026-03-07T10:30:01Z","level":"error","message":"Database timeout"}
# {"timestamp":"2026-03-07T10:30:02Z","level":"info","message":"Retry succeeded"}
```

Each line is a complete JSON object. Consumers process line-by-line without buffering.

### When to Use NDJSON vs JSON Array

| Scenario | Use |
|----------|-----|
| Bounded list of results | JSON array (`[{...}, {...}]`) |
| Streaming/real-time data | NDJSON (one object per line) |
| Large datasets | NDJSON (no memory buffering) |
| Events over time | NDJSON (process as they arrive) |
| Simple API response | JSON array in envelope |

## Flag Conventions for Composability

| Flag | Purpose | Example |
|------|---------|---------|
| `--json` | Structured output | `mycli list --json` |
| `--fields` | Select output columns | `mycli list --fields id,name` |
| `-q, --quiet` | Minimal output (IDs only) | `mycli create -q` → `abc-123` |
| `--no-headers` | Skip table headers | `mycli list --no-headers` |
| `--no-color` | Disable ANSI codes | For piping to files |
| `--no-pager` | Disable interactive pager | For scripts and agents |
| `--stdin` | Read input from stdin | `cat ids.txt \| mycli delete --stdin` |
| `--output` | Output file | `mycli export --output data.json` |
| `--limit` | Limit result count | `mycli list --limit 10` |
| `--sort` | Sort results | `mycli list --sort created_at:desc` |
| `--filter` | Filter results | `mycli list --filter status=active` |

## Composability Checklist

```
[ ] stdout contains only data — no warnings, no progress, no prompts
[ ] stderr receives all non-data output
[ ] Supports --json for structured output
[ ] Supports --quiet for minimal output (IDs/values only)
[ ] Supports reading from stdin (--stdin or - convention)
[ ] Create commands output resource identifiers
[ ] No ANSI codes when stdout is not a TTY
[ ] Supports --no-pager to disable interactive pagers
[ ] Supports --fields to select output columns
[ ] Supports --limit for bounded output
[ ] Exit codes are meaningful (not just 0/1)
[ ] SIGPIPE handled correctly (silent exit, code 141)
```
