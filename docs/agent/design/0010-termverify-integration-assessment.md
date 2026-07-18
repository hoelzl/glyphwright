# TermVerify Integration Readiness — Assessment

| | |
|---|---|
| **Status** | Assessment — a point-in-time survey, subordinate to `0003`; supersedes nothing |
| **Date** | 2026-07-18 |
| **Scope** | Records TermVerify's implementation state, maps it against `0003` §16's integration plan, lists what blocks each adapter flavor, and states GlyphWright's prioritized asks to TermVerify |
| **Authority** | `0003` wins on any disagreement; `0002` records the relationship and ADR-001's integration policy |

TermVerify was surveyed at `hoelzl/termverify` `main` (plus the unmerged
`feat/conpty-adapter-design` branch) on 2026-07-18. Everything below decays as
TermVerify moves; re-verify file-level claims against its tree before acting on them.
TermVerify currently contains **no mention of GlyphWright** — the integration intent is
one-directional, which is exactly why §5's asks need to be delivered, not assumed known.

## 1. TermVerify's state in one paragraph

TermVerify is pre-alpha with no published release. Its **producer half is real and
tested**: an immutable adapter contract (`src/termverify/adapter.py` — `Adapter` and
`ConstraintPorts` protocols plus the value/result types), a working deterministic
in-process runtime (`DirectAdapter` in `src/termverify/direct.py`), a canonical
`termverify.transcript/v1` JSONL codec with an authoritative Python validator
(`src/termverify/transcript.py`, spec in `docs/knowledge/protocol.md`), packaged v1
schemas, and evidence persistence with redaction (`src/termverify/evidence.py`). Its
**consumer/verification half is designed but unimplemented** — no replay engine, no
differential or golden comparison, no property runners, no reports ("Phase 2 is not
active" throughout). A Windows ConPTY binding exists (`src/termverify/_conpty.py`), but
the terminal adapter above it is an accepted, unmerged, unimplemented design
(`docs/agent/design/conpty-adapter-design.md`); POSIX PTY is explicitly deferred.

Two format clarifications that prevent false assumptions:

- TermVerify's transcript JSONL is an **evidence/record format, not a live control
  protocol**. Nothing in TermVerify today speaks JSONL to a child process.
- It is distinct from and does not conflict with GlyphWright's own
  `glyphwright.recording/1` replay format (`0008`), which is engine-side and stays.

## 2. Readiness by adapter flavor (`0003` §16.3)

| Flavor | TermVerify side | Verdict |
|---|---|---|
| 1. Direct (in-process) | `DirectAdapter` works today: implement `DirectApplication` + `ConstraintPorts` over `glyphwright.api`, get validated transcripts out. | **Feasible now** |
| 2. JSONL subprocess (expected workhorse) | No subprocess control transport exists; the contract is a synchronous in-process Python protocol. The bridge from a JSONL-speaking child to port calls would have to be written from scratch. | **Blocked** |
| 3. PTY | ConPTY adapter is design-only, unmerged, Windows-only; the VT normalizer choice (pyte vs in-house) is deferred; the design requires the subject to emit a readiness marker (`"\x1b]7791;ready\x1b\\"`). | **Blocked** |

The verification outcomes GlyphWright actually wants — the right column of `0003`
§16.2 (adapter conformance suite, differential direct-vs-JSONL-vs-PTY runs, reviewed
golden transcripts) — are **all blocked on TermVerify's Phase 2** regardless of
flavor: transcripts can be produced and validated, but nothing yet consumes two of
them and compares, replays one, or renders a report.

Constraint posture is fail-closed and currently narrow (UTC-only timezone, deny-only
network, empty terminal capabilities, manual clock). This costs GlyphWright nothing:
the kernel has no wall clock, no network, and no ambient entropy by construction
(`AGENTS.md` invariants), so GlyphWright is a well-behaved subject under exactly these
constraints. No ask needed here.

## 3. What GlyphWright can do now: the direct-path spike

A producer-side adapter over `glyphwright.api` targeting `DirectAdapter` is buildable
today and is the next integration step:

- Implement `DirectApplication`/`ConstraintPorts` mapping `Engine.step`/`frame`/
  `query`/`fingerprint` onto TermVerify observations and events. Per `0003` §14 the
  mapping must be nearly mechanical; **any logic the adapter needs is evidence of a
  missing `glyphwright.api` capability and is a GlyphWright bug** — surfacing those is
  half the point of the spike.
- The spike is precisely the "evidence of a real conformance suite" that `0003` §20.5
  says must exist before deciding adapter placement and the optional dev-only
  `termverify` extra. Build first, then decide §20.5 — not the reverse.
- Caveats to respect: TermVerify is pre-1.0 with no API stability guarantee, and its
  contract types are not re-exported at package top level (import from
  `termverify.adapter` / `termverify.direct`). The spike must therefore pin the
  TermVerify revision it was built against, and the core suite must keep passing with
  TermVerify uninstalled (ADR-001, `0003` §16.1) whatever the spike's placement.

## 4. Obligations this puts on GlyphWright

- **Readiness marker**: when TermVerify's ConPTY adapter lands, PTY-driving requires
  the subject to emit `"\x1b]7791;ready\x1b\\"` once the first frame is painted. Plan
  this as a `--harness`-gated emission in the TUI (and plain) frontend — cheap, but it
  must not appear in non-harness transcripts or goldens. Do not implement until the
  marker contract is merged on TermVerify's side; re-verify the exact byte sequence then.
- **Version skew discipline** (`0003` §16.4): the spike's conformance material must
  record the TermVerify revision alongside GlyphWright's schema tags, since neither
  side is stable yet.
- Nothing else: the API surface, versioned schemas, session fingerprints, and harness
  meta-channel that the adapter consumes already exist and are golden-tested.

## 5. Prioritized asks to TermVerify

Written to be copied verbatim into a TermVerify issue; GlyphWright is a real external
application under test, so these double as prioritization signal for TermVerify's own
roadmap.

1. **Phase 2 verification core: differential comparison and transcript replay.**
   Highest value, blocks everything. GlyphWright can already produce deterministic,
   schema-tagged frame/event streams from three frontends; what's missing is the
   consumer that takes two transcripts and asserts equivalence, or replays one against
   a subject. Even a minimal comparator over `termverify.transcript/v1` would let a
   GlyphWright direct-adapter conformance suite assert something stronger than "the
   transcript validates."
2. **A subprocess JSONL control transport.** `0003` §16.3 expects the JSONL subprocess
   flavor to be the workhorse (process isolation, full semantic observations, no ANSI
   parsing, composes with sandboxing). Today the only runtime is in-process. A generic
   "spawn a child, exchange line-delimited JSON, adapt to the port protocol" transport
   would serve any JSONL-speaking subject, not just GlyphWright.
3. **Merge and implement the ConPTY adapter, and decide the VT normalizer.** The
   binding is proven; the adapter and normalizer are the missing pieces for
   production-interaction evidence against GlyphWright's TUI. A POSIX PTY story can
   follow later; GlyphWright's primary development host is Windows, so ConPTY-first is
   acceptable.
4. **Package the adapter-author surface.** Re-export the contract (`Adapter`,
   `ConstraintPorts`, `DirectApplication`, value types) at a documented import path
   with a stated (even if pre-1.0) compatibility intent, and add an examples
   directory. GlyphWright's adapter could plausibly *be* the first example — that is
   one of the two §20.5 placement options.

Ordering rationale: (1) is what turns produced evidence into verification at all;
(2) unlocks the workhorse flavor and generalizes; (3) is the flashiest demonstration
but depends on neither; (4) is cheap hygiene that lowers the cost of every external
adapter, ours first.

## 6. Spike results (2026-07-18, same day)

The §3 spike was built and passes: `spikes/termverify-direct-adapter/` maps
`glyphwright.api` onto `DirectApplication`/`ConstraintPorts`, drives a scripted
session through `DirectAdapter` to a clean `RunFinished`, and assembles it into
a `termverify.transcript/v1` that TermVerify's strict codec validates —
byte-identical across identical runs. TermVerify stays a `uv run --with`
overlay; nothing in the package, test suite, or mypy scope touches it.

What the evidence changed:

- **One GlyphWright bug, fixed**: the adapter needed the wire codec, which was
  not on `glyphwright.api`. `decode_command`/`encode_command`/`encode_frame`/
  `encode_event`/`encode_rejection` are now re-exported there (`0003` §14
  updated). Otherwise the mapping was as mechanical as §14 predicted.
- **Ask 1 of issue #114 is now measured**: the spike's `TranscriptRecorder`
  (~120 lines) is the adapter-calls-to-transcript-records harness TermVerify
  does not ship; every adapter author will rewrite it until it exists upstream.
- **§2's constraint-posture claim confirmed**: all seven constraints receipt
  cleanly with zero accommodation; `KeyInput` fails closed as the contract
  demands; rejections map to diagnostics without losing the rejection/refusal
  distinction.
- **§20.5 remains open, as designed**: the spike is placement evidence, not a
  conformance suite. The overlay mechanism shows the "in this repository,
  dev-only, optional" option costs nothing; the code would also drop into a
  TermVerify examples directory unchanged.

## 7. Consequences for the GlyphWright roadmap

Next integration step: the **direct-path adapter spike** (§3), placed per §20.5's
"decide when built" rule. Flavors 2 and 3 and all differential testing wait on
TermVerify regardless of anything GlyphWright does, so engine-side slices (deferred
features: thorns-style hook targeting, XP/progression, additional resource kinds, AI
self-casts) and the graphical-frontend design effort can proceed in parallel without
contention.
