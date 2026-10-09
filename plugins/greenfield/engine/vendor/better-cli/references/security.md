# Security

Secret handling, input validation, and permission scoping for CLIs used by humans and AI agents.

## Secret Handling

### Never Accept Secrets via Flags

Flags are visible in:
- `ps aux` output (anyone on the system can see them)
- Shell history (`~/.bash_history`, `~/.zsh_history`)
- Process monitoring tools
- CI/CD logs (if commands are echoed)

**Bad:**
```bash
mycli login --password "s3cret"    # Visible in ps, history, logs
mycli deploy --api-key "abc123"    # Same problem
```

**Good:**
```bash
# Environment variable
export MYCLI_API_KEY="abc123"
mycli deploy

# File-based
mycli login --password-file ~/.mycli/credentials

# stdin
echo "s3cret" | mycli login --password-stdin

# Interactive prompt (humans only)
mycli login    # Prompts with hidden input
```

### Secret Input Precedence

```
1. --password-file flag     (explicit file path)
2. stdin pipe               (echo "secret" | mycli login --password-stdin)
3. Environment variable     (MYCLI_PASSWORD)
4. OS keychain              (platform-specific credential store)
5. Interactive prompt       (TTY only, hidden input)
```

### Secret Output Rules

1. Never include secrets in `--json` output
2. Never log secrets to stderr (even in `--debug` mode)
3. Mask secrets in error messages: `API key abc...789 is expired` (show only prefix/suffix)
4. Never write secrets to temp files without restrictive permissions (0600)
5. Clear sensitive data from memory after use (language-dependent)

## Input Validation for Agent Contexts

AI agents generate three failure modes that humans rarely produce. Validate defensively.

### Path Traversal

Agents may construct paths that escape intended directories:

```
../../.ssh/id_rsa
../../../etc/passwd
..\..\..\windows\system32\config
```

**Mitigation:**
- Resolve paths to absolute and check they're within the expected directory
- Reject paths containing `..` components
- Use `realpath()` / `path.resolve()` and verify the prefix matches

### Control Character Injection

Agents may include invisible characters in inputs:

```
name: "normal\x00malicious"      # Null byte
name: "normal\x1b[2J"            # ANSI escape (clear screen)
name: "normal\roverwrite"        # Carriage return injection
```

**Mitigation:**
- Strip or reject ASCII control characters (0x00-0x1F, except \n and \t)
- Validate that names match expected patterns: `^[a-zA-Z0-9_-]+$`
- Never pass user input directly to shell commands

### Shell Injection

Agents construct commands and may include shell metacharacters:

```
--name "web-app; rm -rf /"
--name "web-app$(whoami)"
--name "web-app`cat /etc/passwd`"
```

**Mitigation:**
- Use argument arrays, never string interpolation for shell commands
- Validate inputs against strict allowlists
- Reject inputs containing: `; | & $ \` ( ) { } < > \` ! #`

### Double Encoding

Agents may pre-encode values:

```
--name "web%2Dapp"     # Already URL-encoded
--name "web%252Dapp"   # Double-encoded
```

**Mitigation:**
- Normalize inputs before processing
- Detect and reject double-encoded values
- Document whether inputs should be encoded or raw

## Permission Scoping

### Principle of Least Privilege

CLI commands should request only the permissions they need:

```bash
# Bad: one token with all permissions
mycli auth login  # Gets admin token by default

# Good: scoped permissions
mycli auth login --scopes read,deploy    # Only read and deploy
mycli auth login --scopes admin          # Explicit admin request
```

### Token Handling for Agents

When agents use your CLI:

1. **Support service accounts**: Not just human user accounts
2. **Support short-lived tokens**: `--token-ttl 1h` for agent sessions
3. **Support token files**: `--token-file /path/to/token` (not flags or env vars in shared environments)
4. **Log authentication events**: Which token was used, what it did, when

### Audit Trail

For CLIs that perform sensitive operations:

```json
{
  "timestamp": "2026-03-07T10:30:00Z",
  "command": "mycli deploy --env production",
  "user": "service-account-ci",
  "source": "github-actions",
  "result": "success",
  "resources_modified": ["deployment/web-app"]
}
```

## Configuration File Security

### File Permissions

```bash
# Config files containing secrets: owner-only
chmod 600 ~/.config/mycli/credentials

# Config files without secrets: owner read/write, group read
chmod 640 ~/.config/mycli/config.yaml
```

### Warn on Insecure Permissions

```
mycli: warning: Credentials file ~/.config/mycli/credentials has
permissions 0644 (world-readable). Run: chmod 600 ~/.config/mycli/credentials
```

### Config File Locations

Follow XDG Base Directory Specification:

| Purpose | Path | XDG Variable |
|---------|------|-------------|
| Configuration | `~/.config/mycli/` | `$XDG_CONFIG_HOME/mycli/` |
| Data | `~/.local/share/mycli/` | `$XDG_DATA_HOME/mycli/` |
| Cache | `~/.cache/mycli/` | `$XDG_CACHE_HOME/mycli/` |
| State | `~/.local/state/mycli/` | `$XDG_STATE_HOME/mycli/` |

### Environment Variable Caution

Environment variables are inherited by child processes and may be logged:

```bash
# Visible in: child processes, docker inspect, systemd show, /proc/*/environ
export MYCLI_SECRET="abc123"
```

For high-security contexts, prefer:
- OS keychain / credential manager
- Short-lived token files with restrictive permissions
- Encrypted config files

## Security Checklist

```
[ ] Secrets never accepted via command-line flags
[ ] Secrets never appear in stdout or --json output
[ ] Secrets masked in error messages and logs
[ ] Input validated against path traversal
[ ] Input validated against control character injection
[ ] Shell metacharacters rejected in user inputs
[ ] Config files with secrets have 0600 permissions
[ ] Warning emitted for insecure file permissions
[ ] Support for scoped/limited permissions
[ ] Audit logging for sensitive operations
[ ] Token/credential rotation supported
[ ] XDG directory conventions followed
```
