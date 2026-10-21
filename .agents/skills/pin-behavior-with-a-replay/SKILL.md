---
name: pin-behavior-with-a-replay
description: Record a GlyphWright session and replay it to an exact verdict, to prove a run is reproducible or to pin behaviour so a later change cannot alter it unnoticed. Use when you verify a bug fix or a pack, or when the pinned recording test fails.
---

# Pin behaviour with a replay

## 1. Record the session

```bash
uv run glyphwright --record run.jsonl                 # the reference world
uv run glyphwright --pack my-pack --record run.jsonl  # your own pack
```

Play as usual, or pipe a script of commands into it; `quit` ends the
recording. Only accepted commands are recorded. `--record` refuses an
existing file, so pick a new name.

## 2. Replay it

```bash
uv run glyphwright --replay run.jsonl                 # same pack as recorded
```

Exit 0 means `recording verified: N steps, turn T`. Exit 1 names the first
step that diverged, or why the recording does not apply, such as another pack
or another rules revision. Every verdict is listed in
[replay and determinism](../../../docs/knowledge/replay-and-determinism.md#verdicts).

## 3. Use the verdict

- **Proving a fix:** record the run that showed the bug, fix it, and record
  again; the new recording replays, and the step that changed is the fix.
- **Pinning a pack:** commit the recording next to the pack and replay it in
  CI; a change to the pack fails the replay with "recorded against pack".
- **A different machine:** replay there. A verified replay is the evidence
  that the run is the same everywhere.

## 4. When the engine's own pin fails

`tests/test_pinned_recording.py` replays a tour of the reference world. If it
fails after your change:

- the change altered what existing commands produce on purpose: bump `RULES`
  in `src/glyphwright/harness/fingerprint.py`, then run
  `uv run python tests/regenerate_recordings.py`, and commit both;
- you changed the reference pack: only re-record;
- neither was intended: the failure names the first diverging step; find out
  why before you re-record anything.
