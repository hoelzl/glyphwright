---
name: play-a-session
description: Play or drive a GlyphWright session as plain text or JSONL, form valid commands from the frame's grammar, and inspect state with :query. Use when you need to play a world, script a session, or check what the engine does.
---

# Play a session

## 1. Start the engine

```bash
uv run glyphwright                          # plain text, the reference world
uv run glyphwright --frontend jsonl         # one JSON object per line
uv run glyphwright --pack path/to/pack      # your own pack
uv run glyphwright --harness                # also allow :query, :seed, :frame
```

Send one command per line on stdin. `quit` or end of input ends the session.
Add `--seed N` to choose the run's seed; the default is fixed, so a session
is the same every time.

## 2. Form commands from the grammar

Never guess a command. Every frame lists what is valid right now:

- **plain:** type `help` for a list such as `move <exit> | look | wait`;
- **JSONL:** the frame's `commands.verbs` maps each verb to its argument
  domains, for example `{"move": [["east", "south"]], "look": []}`. Build
  `verb argument` from one entry of each domain.

Every command, rejection reason, and query path is in the
[command reference](../../../docs/knowledge/commands.md).

## 3. Read the JSONL stream

The first line is the session header, the second the opening frame. Then,
for each line you send:

- an accepted command: its events, then one frame;
- a refused command: one rejection line with `reason` and `hint`; nothing
  changed and no turn passed;
- a meta command: one line, a query result or a frame.

Every line names its shape and version in `schema`, such as
`glyphwright.frame/N`; branch on the part before the `/`. The schemas are in
`schemas/`. Read lines until the next frame or rejection before sending the
next command.

## 4. Inspect state

With `--harness`, `:query <path>` answers without passing a turn, for example
`:query player.hp` or `:query world.initiative`. Add `--explain` to a stat
path, such as `:query player.stats.atk --explain`, to see every contribution.
An unknown path is an error value, never a crash.

## 5. Check yourself

- Did every command you sent come from the last frame's grammar?
- For a claim about behaviour, quote the event or frame line that shows it,
  not the plain text's wording.
