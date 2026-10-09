---
name: mcp-surface
description: Build and audit the MCP surface so a cold agent uses it right first time. Use when changing an MCP tool, the server's instructions or errors, or what is exposed over MCP.
---

# The MCP surface

The MCP surface (`src/{{package}}/surfaces/mcp.py`) is a projection of the operation catalog: one tool per
operation, named `<noun>_<verb>`, carrying the operation's summary and schema. It holds no logic. A remote agent
sees only what crosses the wire: none of this repository's docs, skills or rules reach it. So everything it
needs has to be in the server.

## Build it for a cold agent

1. Construct the server with an `instructions=` block held in a module constant: what the server is for,
   the entry-point tool to call first, and one thing it is not for. A connecting client receives this and
   nothing else.
2. Every error returns the kernel envelope with `next_step`: the exact tool and arguments that would fix
   it. An error that only says what went wrong leaves the agent to guess.
3. Order is enforced, not documented: an operation that needs another first refuses, naming that one.
4. A thin front door: the entry-point tool returns what exists and which tool goes deeper, not everything.
5. Serve the catalog as resources too (each noun's operations, their effects and their order), so a
   caller can read deeper than the tool list. A server that sends only tools leaves the rest of this
   project unreachable over the wire; the audit flags it.
6. `spend` operations appear only for principals granted spend.

## Audit it

- After each change to the surface, run `/mcp-legibility:legibility-audit --no-headless`. It is static and
  free. It reads the FastMCP constructor from source, including an `instructions=` block held in a
  constant. Tools registered from the catalog in a loop show as zero tools plus a dynamic-registration
  finding, which is expected here: the committed tool list that the surface-parity check holds is the
  static record of what is exposed.
- Before a release, run the headless trial (`/mcp-legibility:legibility-audit` without `--no-headless`).
  It puts a real agent with no context in front of the server and spends a few tens of cents. Ask
  {{owner}} first; never schedule it.
- Record the trial's Prior score in the release's decision record. Prior 0 is the target. A Prior of 4,
  where the agent finished wrongly while reporting success, blocks the release.
