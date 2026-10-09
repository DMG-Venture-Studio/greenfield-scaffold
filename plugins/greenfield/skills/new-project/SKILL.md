---
name: new-project
description: Scaffold a new greenfield project for Claude Code from a spec or a pitch. Confirm the nouns, ways in and add-ons; generate the folder with its architecture, starter checks and planted violations; create the GitHub repository; and hand over the first Claude Code session's prompt. Use when the user wants to start, scaffold, set up or bootstrap a new project or repository, or says "new project", "greenfield" or "scaffold this".
argument-hint: Optional one-line pitch, or the name of a document that describes the project
---

Pitch or document, if given: $ARGUMENTS

Turn the user's intent into a committed project folder whose architecture is fixed by a spec, whose
checks already pass, and whose every check is proven by a planted violation. Leave the user with one
command to run in cmux. A deterministic engine writes every file. This skill only gathers and confirms
the decisions the engine needs, and moves the result to where the user wants it.

## Ground rules

- **The noun list is the decision everything is rendered from.** Never generate before the user has
  confirmed it in so many words.
- **The engine writes the project.** Never hand-write or hand-edit a file the engine generates. If the
  engine refuses the intake, fix the intake and rerun it.
- **Never write into a folder that holds files.** The engine refuses with exit 4. Ask for another
  name; never move or delete what is there.
- Ask with AskUserQuestion, one to four questions a round. Draft two to four concrete options from what
  is known, with the recommended one first and marked. Keep a verbatim record of every question, the
  options and each answer. The record becomes the interview transcript.
- The user is terse and technical. Lead with consequences, never pad, and push back on choices that
  break the conventions. Say which rule is broken and what it costs.

Read `references/intake.md` now. It holds the noun test, the intake file's schema and the defaults.
Read `references/integrations.md` before the add-ons round. Read `references/delivery.md` before
generating.

## 1. Gather the material

1. Take the pitch from the arguments or the conversation. If there is none, ask in one plain message
   what the project is and who it is for. The usual case is a project specced earlier in this same
   conversation, followed by "scaffold it from the docs you made". Then the spec is the pitch, and those
   docs are the first candidates for briefs.
2. Find the documents the user may want dropped in as briefs:
   - files this conversation produced, such as a design doc or a decision ledger written earlier;
   - files attached to this conversation;
   - the attached claude.ai Project's docs (`project_info`, then `project_read`);
   - Docs artifacts named in the conversation.

   Unpack an archive (a zip of docs) into the scratch folder and list the documents inside it. Never pass
   an archive itself as a brief. If the user named docs ("the design and the ledger"), take those without
   asking. Otherwise ask one multiSelect question, "Which documents go into the project as briefs?",
   listing each by name. Selecting none is fine.

   Read every selected document in full and save it verbatim, as Markdown, in a scratch folder
   (`mktemp -d`). Never summarise a brief. The engine files it under the project's decision sources
   exactly as given.

   A Claude Design hand-off prompt is also a brief. It names the `claude_design` MCP and a
   `claude.ai/design/p/...` link. Save it verbatim, and include `web` and `http` in the ways in. Do not try
   to read the design from this session: the claude_design MCP authenticates with `/design-login` in
   Claude Code. The design tool here is for syncing design systems only. The first Claude Code session
   imports the design and builds it as the first slice's page, so name the design file in the first
   gate's or the walking skeleton's description.
3. Read the selected briefs before proposing anything. They usually answer most of the intake.
4. List the briefs' unresolved items: open questions, proposals awaiting a yes, and choices left as A or B.
   - Ask about each one whose answer changes the intake: a noun, a way in, an adapter, the database or
     the first operation. Ask before step 2, in AskUserQuestion rounds, with the brief's own options and
     its recommendation first.
   - The rest stay open, and the first session reads them in the briefs. With serial-build, also write
     each one into `harness.open_questions` as a `## slug` section.

## 2. Propose the architecture

Apply the noun test from `references/intake.md` to the pitch and the briefs. Draft:

- the nouns, each with purpose, owned tables, operations (`noun.verb`), roles and `depends_on`;
- flows, which must span nouns;
- adapters, each an outside service with the import name it wraps and the protocol it implements;
- the ways in (`cli`, `http`, `mcp`, `jobs`, `agent_tools`, `web`);
- the database (`postgres`, `sqlite` or `none`);
- the first operation, which becomes the walking skeleton.

Show the nouns as a compact table in a message: name, purpose, operations, owns, depends on. Then ask
"Are these the nouns?" with "Use them (Recommended)", "Change the nouns" and "Start over". Fold changes
and ask again until the answer is yes. Then ask the ways in (multiSelect), the database and the first
operation in one round.

Push back on these, naming the rule each breaks:
- a noun that is a screen or a table rather than a business thing;
- a verb such as `process`, `handle` or `manage`;
- a flow that touches one noun;
- a dependency ring between nouns;
- `web` without `http`.

## 3. Repository and add-ons

Ask in one or two rounds:

- **Where.** The parent folder, which defaults to the user's projects folder (`~/Dev`), and the folder
  name. The project name, slug and Python package come from the pitch. Offer them as drafted and let
  the user correct them.
- **GitHub.** The owner (their account or an organisation; a GitHub tool's `get_me` gives the
  account), the repository name, and private or public. Private is recommended. Also whether to create
  the remote now. Recommend "now" when a GitHub tool that creates repositories is available, else
  "first session". `references/delivery.md` covers both.
- **Add-ons**, explained from `references/integrations.md`:
  - serial-build, the harness: recommended when one person will run each slice and accept it;
  - agent-skills: recommended;
  - factory: off by default, and say why in one line.

  The kits follow from the spec and need no question: better-cli with a CLI, mcp-legibility with MCP,
  agent-house when an agent or a model adapter exists. State which apply.

## 4. The harness interview (only with serial-build)

Ask one open round in a plain message with no options, because drafted options would put words in the
user's mouth:
- What do the people it is for do today instead, and what does that cost them?
- A year from now, what would failure look like?

Then use AskUserQuestion rounds, with options drafted from everything so far:
- the owner's name (offer the git author name) and how they want to be written to;
- the floors (multiSelect);
- the goals, and what it deliberately is not;
- the first gate. This is the first operation as something the owner does and sees: its demo, ending
  in a `Break it:` step; what the red lane must try in order to break it; and the acceptance sentence;
- the first stage and its goal;
- three to six later gates, one line each.

Read the vision back in five plain lines: what it is; who it is for and what they do today; the first
demo and its break step; what it is not; what failure looks like. Ask "Is this it?" and fold
corrections until the answer is yes.

## 5. Write the intake and dry-run it

Write `<scratch>/intake.json` exactly to the schema in `references/intake.md`. Then find the engine
and a Python of version 3.12 or later:

```bash
ENGINE="${CLAUDE_PLUGIN_ROOT}/engine/scaffold.py"
[ -f "$ENGINE" ] || ENGINE=$(find "$HOME/.claude" "$HOME/mnt" /tmp -path '*greenfield*/engine/scaffold.py' 2>/dev/null | head -1)
py() {
  if python3 -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null; then python3 "$@"
  else uv run --no-project --python 3.12 python "$@"; fi
}
py "$ENGINE" --intake <scratch>/intake.json --dest <scratch>/out/<folder> --dry-run
```

`py` is a function, not a variable, so it works in zsh as well as bash. Define it again in any new
shell.

- **Exit 3** lists every convention the intake breaks. If a fix changes something the user decided, such
  as a noun, ask. Otherwise fix the intake and rerun.
- **Exit 2** names a brief whose file name clashes. Rename the saved brief and rerun.
- **Exit 0** prints JSON: the destination, the plant counts per plants file, and the file list. Summarise
  it in at most eight lines:
  - the nouns and their roles;
  - the ways in;
  - the kits;
  - the plant counts;
  - the add-ons;
  - where it will be written;
  - the remote.

  Ask "Generate it?" with "Generate", "Change something" and "Cancel".

## 6. Generate, commit, link

Follow `references/delivery.md` to pick the path for this session, write the project, commit it and
create or link the remote. Pass `--doc <file>` once for each brief saved in step 1.

## 7. Hand over

Report consequence first, in at most ten lines:
- where the project is;
- what is committed;
- the remote's state;
- the checks:
  - if `references/delivery.md` let you run them, the counts: checks passing, plants caught;
  - otherwise, that the first session runs them in its step 0, and stops if the scaffold fails one;
- the one command that starts the first session, from the project folder in cmux:

  ```
  claude "$(cat docs/decisions/sources/<date>-bootstrap-prompt.md)"
  ```

- what that session does: the push if needed, the plugins, the harness if on, then the enforcement
  build in order.

Then offer, in one line, a weekly scheduled task for the harness audit, using
`tools/toolkit/weekly-harness-audit.md` as its prompt. It needs the repository on GitHub. Create it
only if the user says yes, with the session's scheduling tools.

Do not paste the prompt itself. It is in the project.
