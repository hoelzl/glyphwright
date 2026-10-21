# 0002 — Wire schema tags restart at version 1

How the JSON wire contract is versioned, and why v2's tags do not continue
v0's numbers. Read it before you change an encoder in `src/glyphwright/frontends/wire.py`
or a schema under `schemas/`.

- **Date:** 2026-10-21
- **Status:** accepted

## Context

Every frame, event, rejection, query result, and session header carries a
schema tag such as `glyphwright.frame/1`. The committed JSON Schemas under
`schemas/` are generated from the encoders, and a test fails when the two
disagree.

v0 ended at `glyphwright.frame/6` and `glyphwright.event/9`. v2's first slice
encodes different shapes: no status or mana fields, a grid viewport only, and
three event types. Its contract is not a version of v0's.

## Decision

- **Every tag starts at `/1` in v2.** Continuing v0's numbers would suggest a
  compatibility with v0's consumers that does not exist.
- **Widening a closed shape bumps its tag.** A new field, a new event type, or
  a new viewport kind is a new version, and the schema file is renamed with it
  (`glyphwright.frame.v2.json`).
- **Old tags are retired, not kept alongside.** Until an outside consumer
  depends on the stream, there is nothing to stay compatible with, so a bump
  replaces the old schema instead of adding a compatibility matrix. That
  changes with the first outside consumer, which gets its own decision record.

## Consequences

- Regenerate the committed schemas with
  `uv run python -m glyphwright.harness.schema` and review the diff; the test
  suite fails until the committed files match.
- Later slices will bump `frame` and `event` several times before S5. That is
  expected and cheap while no one outside the project reads the stream.
