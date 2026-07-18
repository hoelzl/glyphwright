# Spike: GlyphWright under TermVerify's direct adapter

The first real integration between the two projects: `glyphwright.api` mapped
onto TermVerify's in-process producer contract (`DirectApplication` +
`ConstraintPorts`, driven by `termverify.direct.DirectAdapter`), with the
session assembled into a `termverify.transcript/v1` that TermVerify's own
strict codec validates. Context and asks: design `0010`; the TermVerify-side
prioritization issue is `hoelzl/termverify#114`.

## Run it

From the repository root, with a TermVerify checkout as a sibling directory
(`../termverify`):

```
uv --no-config run --with ../termverify python spikes/termverify-direct-adapter/run_spike.py
```

TermVerify is a `uv run --with` overlay — never a project dependency. The core
suite neither imports nor needs it (`0003` ADR-001); this spike directory is
not part of the package, the test suite, or the mypy scope.

## What it proves

- All seven constraints negotiate to receipts and the run reaches readiness.
  GlyphWright is a well-behaved subject under TermVerify's fail-closed posture
  without any accommodation: seed is a real injection, everything else
  (clock, locale, timezone, filesystem, network) is vacuously true of a kernel
  that has no clock, no ambient entropy, and no I/O.
- A scripted session — accepted commands, a typed rejection (`move nowhere`),
  an unparsable line (`dance`), a resize, a clock advance, a stop — runs to a
  clean `RunFinished` with exit code 0.
- GlyphWright's semantics survive the mapping losslessly: engine events become
  observation events; typed rejections and unparsable input become
  diagnostics (`command-rejected`, `command-unparsable`) on a quiescent epoch,
  exactly matching `0003` appendix A.4's "the engine never ran the command";
  a world-refusal (walking into a wall) stays an ordinary event-bearing epoch.
- Two identical runs serialize to **byte-identical** canonical transcripts
  (RFC 8785), and `parse_transcript` accepts them. `transcript.jsonl` is the
  committed output — illustrative evidence for review, not a golden that
  gates anything.
- A semantic key chord (`Control+c`) fails closed as
  `adapter-runtime-failed` / `{"input_kind": "key", "reason": "unsupported"}`
  rather than being translated — keys exist only in the TUI (`0003` ADR-003),
  and the direct-adapter contract forbids silent translation.

## Findings

**GlyphWright bug found and fixed (0003 §14's own rule):** the adapter needed
`decode_command` / `encode_frame` / `encode_event` / `encode_rejection`, which
lived only in `glyphwright.frontends.wire`. The wire codec is now re-exported
from `glyphwright.api`; the only remaining reach past the API is
`frontends.plain.render`, deliberately, as this adapter's declared normalizer.

**The mapping is as mechanical as §14 predicted.** `glyphwright_application.py`
is ~230 lines, none of them game logic: receipts echo requests, `step` results
fan out into observation fields, and quiescence is trivial because the engine
is synchronous.

**TermVerify's missing consumer side is now measured, not asserted.**
`TranscriptRecorder` in `run_spike.py` (~120 lines) is the piece TermVerify
does not ship: nothing turns adapter calls into transcript records. Every
adapter author will write this same class until TermVerify provides it —
concrete evidence for issue #114's ask 1.

**Version skew is expressible today.** The transcript's replay subject carries
the GlyphWright version and the frame schema version
(`state_schema: glyphwright.frame/5`), so `0003` §16.4's compatibility matrix
has a place to live once a real conformance suite exists.

## Non-goals

Adapter placement (`0003` §20.5) is still deliberately open — this spike is
evidence for that decision, not the decision. No differential testing, no
replay, no PTY: all blocked on TermVerify's side (design `0010` §2).
