---
name: credentials
description: Declare, mint, rotate and audit this project's API keys in Infisical with tools/toolkit/credentials.py. Use when an adapter starts needing a key, a key leaks or someone leaves, a deploy reports an auth failure, or before naming a key in code or docs.
---

# Credentials: declared here, valued in Infisical, minted by a person

Every key the project uses is a row in `credentials.toml`: its variable name, its vendor, the adapter that
reads it, the Infisical folder and environments it lives in, and how long it may live. The value is only
ever in Infisical and in the deployed service's variables. `credentials.py check` holds the first half:
every adapter that wraps a vendor SDK has a row, and nothing git would commit holds the shape of a key.

## Rules for an agent

- Never ask for, paste, print or read a key's value. Not in chat, a file, a test, a fixture or argv.
- A new adapter that needs a key gets its row in `credentials.toml` in the same change, and `check` passes.
- Code reads the key from the environment by the row's name, in the adapter, and nowhere else.
- Minting is a person's job. Tell {{owner}} which command to run; never drive a vendor's dashboard.
- A key the check finds in the tree has been on disk: say so, and ask {{owner}} to rotate it. Deleting
  the line does not un-leak it.

## Commands

All run from the repository root, with `uv run python tools/toolkit/credentials.py` before each:

```
check                                   the manifest agrees with the spec; no key shape in the tree
provision --env staging                 mint each key staging lacks: open the page, copy, Enter
rotate ANTHROPIC_API_KEY --env prod     replace one key; Infisical keeps the old version for rollback
adopt ANTHROPIC_API_KEY --env prod      record a mint date for a key that was imported, not minted
probe ANTHROPIC_API_KEY --env staging   call the vendor with the stored key
audit --json audit.json                 every key present, and inside its rotation window
```

`provision` and `rotate` read the key from the clipboard, call the vendor with it, store it with its mint
date and fingerprint, then clear the clipboard. A key that fails its vendor's check is never stored.
They act as the person signed in with `infisical login`, or as a machine identity through `INFISICAL_TOKEN`.

## Setting it up once

1. In Infisical, create the project `{{slug}}` with the environments in `credentials.toml`, and put the
   instance URL and the project's ID under `[manager]`.
2. One vendor workspace or project per environment where the vendor has them (Anthropic, OpenAI), each
   with its own spend cap, named `{{slug}}-<environment>`. A loop on staging then cannot spend
   production's budget, and revoking a staging key never touches production.
3. `provision --env dev`, then staging, then prod.
4. In Infisical, Integrations, Secret Syncs: one Railway sync per environment and folder, to that
   Railway environment and service. Its Railway connection needs an account or workspace token; project
   tokens do not work with Railway's public API. Turn on Disable Secret Deletion, so the sync never removes
   the variables Railway manages itself, such as a database reference. Check the service's variables in
   Railway after the first staging sync, before you trust it with production.

## Rotation

Production keys rotate on events: a leak, someone leaving, a vendor's breach notice. Other environments
also rotate on the calendar in `rotate_days`; Infisical emails a reminder when one is due, if its SMTP is
set. Order matters: `rotate`, let the sync push the new value and the service redeploy, confirm with
`probe`, then revoke the old key at the vendor. `rotate` prints the old key's last four characters so
you can find it there.
