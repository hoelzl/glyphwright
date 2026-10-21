# Replay and determinism

The determinism contract, the recording format, what replay verifies, and the
rules revision that a pinned recording guards. Read it when you record or
replay a session, when you pin behaviour with a recording, or when the pinned
recording fails.

## Contents

- [The contract](#the-contract)
- [Recording and replaying](#recording-and-replaying)
- [The recording format](#the-recording-format)
- [Verdicts](#verdicts)
- [The rules revision and the pin](#the-rules-revision-and-the-pin)

## The contract

A run is fully determined by the rules revision, the pack id, the seed, and
the command sequence. Everything else, every event, frame, and state, is
derived from those four, so a run can be stored as them and checked by
re-running it. What makes this hold:

- `step` is pure, and the core does no ambient I/O; a test scans its imports
  ([`docs/knowledge/kernel.md`](kernel.md)).
- All randomness comes from the seeded PCG64 cursor in the state, and every
  draw is folded back through the round's closing `TurnAdvanced`.
- The successor state is the fold of the events, which the property walks
  check after every step.

## Recording and replaying

```bash
uv run glyphwright --record run.jsonl     # play, and record the session
uv run glyphwright --replay run.jsonl     # verify it: exit 0 or 1
```

`--record` refuses an existing file: a recording is a run from turn 0.
`--replay` takes the seed from the recording and checks it against the pack
you pass with `--pack`, or the reference pack. It refuses `--seed` and
`--record`, and ignores `--frontend` and `--harness`.

## The recording format

JSON lines, in canonical JSON (sorted keys, compact):

1. a `glyphwright.session/2` header: `engine`, `rules`, `pack`, `seed`,
   `harness`;
2. one `glyphwright.recording/1` line per accepted step: `step` (from 1),
   `command` as typed, and `events`, a SHA-256 digest of the step's encoded
   events.

Rejected commands and meta commands change nothing, so they are not recorded.
Both schemas are committed under `schemas/`. A UTF-8 byte-order mark at the
start, as some editors write it, is ignored.

## Verdicts

Replay never raises on a bad recording; it returns a verdict.

| Verdict | Meaning |
|---|---|
| `recording verified: N steps, turn T` | every step produced the recorded events |
| `recorded under rules A, replaying under rules B` | the engine's behaviour changed since it was recorded |
| `recorded against pack …` | the content is not the content it was recorded against |
| `step N: '…' produced different events than recorded` | the first step that diverged |
| `step N: '…' was rejected (…)` | the run took a path this engine refuses |
| a header or line problem | the file is not a recording, or was edited by hand badly |

The release version in `engine` is recorded but not compared: a release need
not change behaviour.

## The rules revision and the pin

`RULES` in `src/glyphwright/harness/fingerprint.py` names the engine's
behaviour ([decision 0003](../decisions/0003-rules-revision.md)). Bump it in
any change that makes the same commands produce different events.

`tests/recordings/reference-tour.jsonl` is the pin: a tour of the reference
world that takes and equips items, wins a battle, crosses a portal, and flees.
`tests/test_pinned_recording.py` replays it, so an accidental behaviour change
fails the suite. When it fails:

- **Behaviour changed on purpose:** bump `RULES`, run
  `uv run python tests/regenerate_recordings.py`, and commit both.
- **The reference pack changed:** only re-record; content is not behaviour.
- **Neither was intended:** the failure names the first step that diverged;
  that is where to look.

Event digests do not cover frames, so a change to frames alone, such as a
message's wording, needs no bump; the goldens catch it.
