# Delivery: writing the project where the user works

The engine needs Python 3.12 and writes into an empty folder. Pick the first of these paths that fits
this session, and use only that one.

## The remote first

Do this before any path, when the user chose to create the remote now. If a GitHub tool that creates
repositories is available (a GitHub connector's `create_repository`, possibly behind a device prefix),
call it with:
- `name`;
- `organization`, left out for the user's own account;
- `private`;
- `autoInit: false`, so the scaffold's commit is the first;
- a one-sentence `description`.

On success, set `repo.remote` to `created` in the intake. If no such tool exists, or the call fails,
set `to-create`; the first session then runs `gh repo create ... --source . --remote origin --push` on
the user's machine, where `gh` is signed in. Never ask the user for a token.

## Path A: this session's shell can see the destination

This is the case when Claude Code runs on the user's machine, or in a desktop session whose shell
mounts the user's folders under `$HOME/mnt/<folder>`. Check with `ls` on the parent folder.

```bash
py "$ENGINE" --intake <scratch>/intake.json --dest <parent>/<folder> --git [--doc <brief>]...
```

- Exit 0: written, committed (`Scaffold <name>`), with `origin` added when an owner was given and the remote is not `none`.
- Exit 5: the files are written but a git step failed; the message names the step.
  - A failure removing a lock file means deletion is blocked in that folder. Ask once for permission to
    delete in the parent folder, with the reason "git removes its own lock files while it commits".
  - If granted, remove the stale `.git` directory the failed step left, and rerun only the git part:
    `git init -q -b main && git add -A && git commit -q -m "Scaffold <name>"`, then
    `git remote add origin https://github.com/<org>/<name>.git`.
  - If declined, leave it. The bootstrap prompt's step 0 initialises and commits on the user's machine.
- Then try `git push -u origin main` once if the remote was created. An authentication failure is
  expected here and is not an error: the first session pushes.
- If `uv` is on this shell's path, run the scaffold's checks now and report the counts:
  - `uv sync`;
  - `uv run python tools/toolkit/prove_checks.py plants.toml`;
  - with `web`, also `(cd web && npm install)` and `uv run python tools/toolkit/prove_checks.py web/plants.toml`.

  If any check fails on the untouched scaffold, report it as a scaffolder bug, with the output. Do not
  patch the project.

## Path B: the destination is on the user's computer, reached through device tools

Use this when the session runs in the cloud and the user's folders are reachable only through device
tools: a device shell, `device_commit_files` and `device_list_dir`.

1. Confirm the parent is a connected folder (`get_device_info`). If it is not, request access to it
   once, naming why.
2. Run the engine here into a staging folder, without `--git`:
   `py "$ENGINE" --intake ... --dest /mnt/user-data/outputs/<folder> [--doc ...]`.
3. Copy every file to the device with `device_commit_files`: `stagedPath` is the staged file, and
   `devicePath` is `<parent>/<folder>/<same relative path>`. At most 50 files go in one call, so split
   the list.
4. Verify the copy with the device shell: `find <folder> -type f | wc -l` must equal the engine's count.
   A difference is fixed by recommitting the missing files, never by writing them by hand.
5. Git on the device: run the commands from Path A's exit 5 handling in the device shell, including the
   one request for permission to delete, which git needs for its own lock files. If deletion is declined,
   skip git; the first session does it.

## Path C: nothing reaches the user's folders

Run the engine into the staging folder, zip it, and send the zip with SendUserFile. Tell the user:
- unzip it into the parent folder;
- `cd` into the project;
- run the bootstrap command.

The bootstrap's step 0 initialises git and creates the remote.
