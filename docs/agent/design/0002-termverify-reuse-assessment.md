# TermVerify relationship and reuse assessment

Status: revised 2026-07-17 to agree with `0003-glyphwright-design.md`, which is authoritative.
The relationship itself is fixed by `0003` ADR-001; this document records only provenance of
influences and the licensing position.

## Relationship

GlyphWright is an exemplary application under test for [TermVerify](https://github.com/hoelzl/termverify): agents drive the real terminal interface while also comparing it against direct semantic observations. GlyphWright is deliberately **not** a TermVerify component. It is an independent application whose design demonstrates what a well-behaved, verifiable terminal application looks like, and thereby exercises TermVerify's claim of being harness-neutral.

## Reuse and provenance

Candidate concepts are TermVerify's direct semantic adapter, PTY driving, deterministic run configuration, semantic observations, replay transcripts, and reviewed evidence. TermVerify is Apache-2.0, compatible with GlyphWright's Apache-2.0 license.

No TermVerify source is copied. GlyphWright adopts only general architectural ideas: explicit determinism, semantic evidence before raw terminal snapshots, and separation of a pure core from terminal I/O. `0003` §3 records how each TermVerify principle translates into an engine requirement. This document and its links provide provenance for those influences.

## Integration policy (ADR-001)

**Engine code never imports `termverify`, and the shipped package carries no runtime dependency on it.** This is permanent and binds the distribution: GlyphWright must be installable and usable with TermVerify absent.

The direction is enforced mechanically rather than by discipline (`0003` §16.1):

1. An import-linter contract in CI forbids `glyphwright.* → termverify.*`.
2. A dedicated CI job runs GlyphWright's core test suite in a bare environment without TermVerify installed.

### What is deliberately still open

ADR-001 binds engine code, not the test tree. Two questions are **not** decided and should not be decided in advance (`0003` §20.5):

- Where the producer-side adapter over `glyphwright.api` lives — TermVerify's examples directory, or this repository's test/integration tooling.
- Whether this repository may take `termverify` as an optional, dev-only dependency to run adapter or differential tests.

Decide both when the adapter is actually built, against a real conformance suite. Do not make a moving development checkout or an unpublished TermVerify protocol a hidden dependency of the engine; an explicit, documented, optional dev extra is a different thing and remains available. Whatever is chosen, the core suite must still pass with TermVerify uninstalled.

The obligations this creates on GlyphWright are to keep `glyphwright.api` and the wire formats versioned, documented contracts, to retain subprocess/PTY proof of the shipped interface, and to manage adapter/engine version skew explicitly through schema tags (`0003` §16.4). If the adapter ever needs real logic, the fault is a missing capability in `glyphwright.api` — a GlyphWright bug, not an adapter concern.
