# Session Recording and Replay — Design Document

| | |
|---|---|
| **Status** | Accepted — subordinate to `0003`; resolves `0003` §20.2 |
| **Date** | 2026-07-18 |
| **Scope** | The durable run format and its verification (slice 11) |
| **Authority** | `0003` wins on any disagreement; this document only refines it |

`0003` §20.2 asked: opaque pickle of `WorldState` (fast, version-fragile) or
event-log-plus-prefix-hash (robust, slower restore)? The proposal — **replay
as the durable format, in-memory state sharing as the fast path** — is
adopted. A run *is* (engine version, pack hash, seed, commands) (`0003` §5.2);
everything else is derivable, so everything else is verification, not state.

## 1. The recording format (`glyphwright.recording/1`)

A recording is JSON lines:

- **Line 1**: the existing `glyphwright.session/1` header, verbatim — engine
  version, pack id, seed. The header *is* the compatibility contract: replay
  refuses a recording whose engine string, pack id, or seed do not match the
  session it would replay into. No new header schema.
- **One line per accepted step**:
  `{"schema": "glyphwright.recording/1", "step": N, "command": "<command language>", "events": "sha256:…"}`.
  The command is the round-trippable command language (`0003` §6) — the same
  text a player would type, so recordings are human-readable and hand-
  editable. `events` is the SHA-256 over the step's canonically encoded
  event list (the §20.2 "prefix hash", per step): replay does not trust
  determinism, it verifies it.
- Rejected commands are not recorded: the engine never ran them, so they
  are not part of the run. Meta-channel queries are not steps at all.
  Accepted observations (`look`) are recorded like any other accepted
  command — the recording is the accepted command sequence, nothing
  cleverer, and a no-op step verifies trivially (its digest covers an
  empty event list).

## 2. Replay

`replay(pack, lines)` checks the header against the pack and the running
engine version, rebuilds `Engine.new(pack, seed)`, re-executes each command,
and compares each step's event digest. The outcome is data
(`Replay(ok, steps, problem, engine)`): a divergence names the step and what
went wrong (undecodable command, rejection, digest mismatch) rather than
raising — a harness asserts on it, a human reads it.

- **Restore is replay**: the returned engine stands at the recording's final
  state, and fold-equivalence (`0003` §5.3) guarantees byte-exact state,
  RNG cursor included. The fast path needs no format at all: the existing
  in-memory `Engine.snapshot()`/`Engine.restore()` pair *is* the fast path
  (state is immutable, so a snapshot is free), and it deliberately never
  touches disk.
- **Version fragility is the point**: a recording made by a different engine
  version or pack refuses loudly instead of replaying subtly wrong. That is
  the fingerprint doing its §14 job; there is no cross-version migration
  story, deliberately.

## 3. Surface

- `wire.encode_command` — the command language's writing half (the echo
  renderer moves out of `api`; `decode(encode(c)) == c` for every command).
- `harness/recording.py` — `events_digest`, `step_line`, `replay`, and
  `RecordingEngine` (an `Engine` that appends header and step lines to a
  sink as it goes; frontends need no changes).
- CLI: `--record PATH` writes while any frontend plays; `--replay PATH`
  verifies a recording against the chosen pack and exits 0 on a verified
  replay, 1 with a diagnostic otherwise.
- Schema: the step line is generated and committed as
  `glyphwright.recording.v1.json` like every wire type.

## 4. Non-goals

Cross-version migration, snapshot compression, partial replays (prefixes
verify trivially by truncation — cutting a recording short is editing it,
not a feature), and replaying rejections.
