# Testing

Output contract testing, CLI integration tests, snapshot testing, and schema validation.

## Output Contract Testing

Your `--json` output is an API contract. Test it like one.

### JSON Schema Validation

Define a JSON Schema for each command's output and validate in CI:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["status", "data"],
  "properties": {
    "status": { "enum": ["ok", "error"] },
    "data": {
      "type": "object",
      "required": ["id", "name", "status"],
      "properties": {
        "id": { "type": "string" },
        "name": { "type": "string" },
        "status": { "type": "string", "enum": ["running", "stopped", "error"] }
      }
    }
  }
}
```

### Contract Test Pattern

```bash
# Run command and capture output
mycli deploy --env staging --json > output.json

# Validate against schema
ajv validate -s schemas/deploy-output.json -d output.json

# Or in test code (Node.js example)
const output = JSON.parse(execSync('mycli deploy --env staging --json'));
expect(output).toMatchSchema(deployOutputSchema);
```

### What to Test in Contracts

1. **Required fields are present** in every response
2. **Field types are consistent** (id is always string, count is always number)
3. **Enum values are within the documented set**
4. **Error responses use the error envelope** (not raw strings)
5. **New fields don't break existing consumers** (additive-only changes)

## CLI Integration Testing

### Pattern: Subprocess Testing

Run your CLI as a subprocess and assert on exit code, stdout, and stderr:

```python
import subprocess

def test_deploy_requires_env():
    result = subprocess.run(
        ['mycli', 'deploy'],
        capture_output=True, text=True
    )
    assert result.returncode == 2  # Usage error
    assert '--env' in result.stderr
    assert result.stdout == ''  # No data output on usage error

def test_deploy_dry_run_json():
    result = subprocess.run(
        ['mycli', 'deploy', '--env', 'staging', '--dry-run', '--json'],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data['status'] == 'ok'
    assert data['dry_run'] is True
    assert isinstance(data['changes'], list)
```

### Pattern: Exit Code Testing

Test every documented exit code:

```python
def test_exit_code_success():
    result = run(['mycli', 'status'])
    assert result.returncode == 0

def test_exit_code_usage_error():
    result = run(['mycli', 'deploy', '--unknown-flag'])
    assert result.returncode == 2

def test_exit_code_not_found():
    result = run(['mycli', 'get', '--id', 'nonexistent'])
    assert result.returncode == 3

def test_exit_code_permission():
    result = run(['mycli', 'admin', '--no-auth'])
    assert result.returncode == 4
```

### Pattern: Stream Separation Testing

Verify that data goes to stdout and diagnostics go to stderr:

```python
def test_stdout_contains_only_data():
    result = run(['mycli', 'list', '--json'], capture_output=True)
    # stdout must be valid JSON (no warnings, no progress)
    data = json.loads(result.stdout)
    assert data['status'] == 'ok'

def test_stderr_contains_warnings():
    result = run(['mycli', 'list', '--deprecated-flag'], capture_output=True)
    assert 'warning' in result.stderr.lower()
    # stdout should still be valid data
    json.loads(result.stdout)  # Must not raise
```

### Pattern: Non-TTY Behavior Testing

Verify the CLI behaves correctly when not connected to a terminal:

```python
def test_no_ansi_in_pipe():
    result = run(['mycli', 'list'], capture_output=True, text=True)
    # No ANSI escape codes in piped output
    assert '\x1b[' not in result.stdout
    assert '\x1b[' not in result.stderr

def test_no_prompt_in_pipe():
    result = run(
        ['mycli', 'delete', '--id', 'abc'],
        capture_output=True, text=True,
        input=''  # Empty stdin, not a TTY
    )
    # Should fail with clear error, not hang
    assert result.returncode != 0
    assert '--yes' in result.stderr or '--force' in result.stderr
```

## Snapshot Testing

Capture and version the human-readable output format:

### Pattern: Help Text Snapshots

```python
def test_help_output(snapshot):
    result = run(['mycli', '--help'], capture_output=True, text=True,
                 env={**os.environ, 'NO_COLOR': '1'})
    assert result.stdout == snapshot

def test_deploy_help(snapshot):
    result = run(['mycli', 'deploy', '--help'], capture_output=True, text=True,
                 env={**os.environ, 'NO_COLOR': '1'})
    assert result.stdout == snapshot
```

### Pattern: Error Message Snapshots

```python
def test_missing_required_flag_message(snapshot):
    result = run(['mycli', 'deploy'], capture_output=True, text=True,
                 env={**os.environ, 'NO_COLOR': '1'})
    assert result.stderr == snapshot
```

### Snapshot Rules

1. Always set `NO_COLOR=1` in snapshot tests — ANSI codes make diffs unreadable
2. Snapshot both `--help` output and error messages
3. Update snapshots intentionally — review diffs carefully
4. Don't snapshot timestamps or dynamic values — strip or mock them

## Schema Validation in CI

### CI Pipeline Integration

```yaml
# .github/workflows/cli-contracts.yml
name: CLI Output Contracts
on: [push, pull_request]
jobs:
  contracts:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build CLI
        run: make build
      - name: Validate JSON schemas
        run: |
          for schema in schemas/*.json; do
            command=$(basename "$schema" .json)
            ./mycli "$command" --json --test-fixture | \
              ajv validate -s "$schema" -d -
          done
      - name: Run contract tests
        run: make test-contracts
      - name: Check help text snapshots
        run: make test-snapshots
```

### Breaking Change Detection

```bash
# Compare current output schema against baseline
mycli list --json --test-fixture > current.json
diff <(jq 'keys' baseline.json) <(jq 'keys' current.json)

# If keys were removed, it's a breaking change
# If keys were added, it's a safe change
```

## Testing Checklist

```
[ ] JSON output validates against documented schema
[ ] Every documented exit code has a test
[ ] stdout contains only data (no warnings/progress mixed in)
[ ] stderr contains diagnostics (errors, warnings)
[ ] No ANSI escape codes when stdout is not a TTY
[ ] No hanging prompts when stdin is not a TTY
[ ] --help output has a snapshot test
[ ] Error messages have snapshot tests
[ ] --json envelope shape is consistent across all commands
[ ] New fields don't break existing schema validation
[ ] Schema validation runs in CI on every PR
```
