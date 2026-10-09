# Interactivity

TTY detection, NO_COLOR implementation, progress indicators, and prompt design.

## TTY Detection

The foundation of dual-audience CLI design: detect whether output is going to a human terminal or a pipe/file.

### Implementation by Language

**Node.js**
```javascript
const isInteractive = process.stdout.isTTY === true;
const noColor = 'NO_COLOR' in process.env || process.env.TERM === 'dumb';
const isCI = process.env.CI === 'true' || process.env.CI === '1';

if (!isInteractive || noColor) {
  // Plain output, no colors, no spinners, no prompts
}
```

**Python**
```python
import sys, os

is_interactive = sys.stdout.isatty()
no_color = 'NO_COLOR' in os.environ or os.environ.get('TERM') == 'dumb'
is_ci = os.environ.get('CI') in ('true', '1')

if not is_interactive or no_color:
    # Plain output mode
```

**Go**
```go
import (
    "os"
    "golang.org/x/term"
)

isInteractive := term.IsTerminal(int(os.Stdout.Fd()))
_, noColor := os.LookupEnv("NO_COLOR")
isCI := os.Getenv("CI") == "true"
```

**Rust**
```rust
use std::io::IsTerminal;

let is_interactive = std::io::stdout().is_terminal();
let no_color = std::env::var("NO_COLOR").is_ok();
let is_ci = std::env::var("CI").map(|v| v == "true").unwrap_or(false);
```

### Behavior Matrix

| Condition | Colors | Progress | Prompts | Default Output |
|-----------|--------|----------|---------|----------------|
| TTY + no env overrides | Yes | Yes | Yes | Human-formatted |
| TTY + NO_COLOR | No | Yes | Yes | Human-formatted, no color |
| Not TTY (pipe/file) | No | No | No | Plain text |
| Not TTY + --json | No | No | No | JSON |
| CI=true | No | No | No | Plain text |

### Check Priority

```
1. --json flag           → JSON mode (overrides everything)
2. --no-color flag       → Disable color (flag overrides env)
3. NO_COLOR env var      → Disable color
4. FORCE_COLOR env var   → Force color even in pipe
5. TERM=dumb             → Minimal mode (no color, no fancy output)
6. CI=true               → Non-interactive mode
7. !isatty(stdout)       → Pipe mode (no color, no progress, no prompts)
8. Default               → Full interactive mode
```

## NO_COLOR Implementation

The NO_COLOR standard (https://no-color.org/): when the `NO_COLOR` environment variable is present and non-empty, suppress ANSI color output.

### Rules

1. Check for `NO_COLOR` before emitting any ANSI codes
2. Any non-empty value means "no color" — don't check for specific values
3. `NO_COLOR` applies only to color — bold, underline, and italic are still allowed
4. User-level flags (`--no-color`, `--color`) may override `NO_COLOR`
5. Also respect `FORCE_COLOR` for the opposite case (force colors in pipes)

### Related Environment Variables

| Variable | Meaning | Precedence |
|----------|---------|------------|
| `NO_COLOR` | Disable color (any non-empty value) | Standard |
| `FORCE_COLOR` | Force color even in pipes | Overrides NO_COLOR |
| `CLICOLOR=0` | Disable color (older convention) | Below NO_COLOR |
| `CLICOLOR_FORCE=1` | Force color (older convention) | Below FORCE_COLOR |
| `TERM=dumb` | Minimal terminal — no formatting | Independent signal |

## Color Usage

### Semantic Color Assignments

| Color | Meaning | Use For |
|-------|---------|---------|
| Red | Error, danger | Error messages, failed tests, destructive actions |
| Yellow | Warning, caution | Warnings, deprecation notices |
| Green | Success, positive | Success messages, passed tests, created resources |
| Blue | Information | Informational messages, links |
| Dim/Gray | De-emphasized | Metadata, timestamps, secondary info |
| Bold | Emphasis | Key values, resource names, important flags |

### Rules

1. Never use color as the ONLY way to convey information (accessibility)
2. Use color sparingly — if everything is colored, nothing stands out
3. Red should be reserved for genuine errors, not just emphasis
4. Always test with `NO_COLOR=1` to ensure output is still readable

## Progress Indicators

### For TTY (Humans)

**Spinner** — for unknown-duration tasks:
```
⠋ Connecting to API...
⠙ Authenticating...
✓ Connected successfully
```

**Progress bar** — for measurable work:
```
Downloading  [████████░░░░░░░░] 50%  125/250 MB  ETA: 30s
```

**X of Y** — for countable items:
```
Processing: 42/100 files  [████████░░░░] 42%
```

### For Non-TTY (Agents/Pipes)

Option 1: **Suppress entirely** (simplest, usually best)

Option 2: **Simple line-based progress to stderr**
```
[progress] 25% Downloading dependencies...
[progress] 50% Building application...
[progress] 75% Running tests...
[done] Build completed in 42s
```

Option 3: **Structured progress to stderr**
```json
{"type": "progress", "percent": 25, "message": "Downloading..."}
{"type": "progress", "percent": 50, "message": "Building..."}
{"type": "complete", "duration_ms": 42000}
```

### Rules

1. Progress ALWAYS goes to stderr — never contaminate stdout
2. Use `\r` (carriage return) for in-place updates on TTY, never on pipes
3. Suppress progress entirely when stdout is not a TTY unless `--progress` is explicit
4. Include an ETA when possible
5. Clear the progress indicator on completion (show checkmark or "Done")
6. Don't update faster than 10Hz — wastes cycles and causes flicker

## Prompt Design

### Prompt Types and Flag Equivalents

| Type | TTY Behavior | Non-TTY Behavior | Flag |
|------|-------------|------------------|------|
| Yes/No | Interactive confirm | Fail or use `--yes` | `--yes`, `--force` |
| Text input | Interactive readline | Fail or use flag | `--name=value` |
| Password | Hidden input | Read from file/stdin | `--password-file` |
| Selection | Arrow-key menu | Fail or use flag | `--type=value` |
| Multi-select | Checkbox menu | Fail or use flag | `--features=a,b,c` |

### Prompt Rules

1. Every prompt MUST have a flag equivalent — no exceptions
2. If stdin is not a TTY and no flag is provided, print a clear error to stderr:
   ```
   Error: --env flag is required in non-interactive mode.
   Usage: mycli deploy --env <staging|production>
   ```
3. Never hang waiting for input in a pipe — detect and fail fast
4. Mask password input (don't echo characters)
5. Show the default value in brackets: `Environment [staging]:`
6. For destructive actions, require typing the resource name:
   ```
   Type "production-db" to confirm deletion:
   ```
   With flag bypass: `--confirm=production-db`

### Dangerous Action Confirmation Scale

| Severity | Example | Prompt Level |
|----------|---------|-------------|
| Low | Overwrite a local file | Simple y/n, default No |
| Medium | Delete a deployment | y/n, default No |
| High | Delete production data | Type resource name to confirm |
| Critical | Destroy entire environment | Type resource name + `--env` flag |

All levels must support `--yes` / `--force` bypass for automation.
