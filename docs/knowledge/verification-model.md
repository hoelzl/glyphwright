---
type: concept
title: Verification model
description: Layered evidence for deterministic RPG semantics and terminal interaction, and the GlyphWright/TermVerify boundary.
tags: [verification, replay, terminal, testing, termverify]
---

# Verification model

Authoritative source: `docs/agent/design/0003-glyphwright-design.md` §16–§17.

GlyphWright separates semantic correctness from interface operability. Structured frames and typed events are the canonical observations; rendered text is derived material, covered by a small set of reviewed goldens per frontend to catch layout regressions. Raw terminal bytes are necessary interface evidence but never the sole oracle.

## Engine-side evidence

- **Unit tests** prove individual commands, terrain rules, and event semantics.
- **Property/invariant tests** walk random valid commands generated from the frame's `CommandGrammar`, asserting invariants: HP within bounds, inventory conservation, no movement through impassable positions, the mode stack never underflows, every event applies cleanly.
- **Determinism tests** assert that identical `(pack, seed, commands)` yields identical frame and event sequences, and that replay-from-log equals snapshot/restore.
- **Purity tests** assert `step` does not mutate its input state.
- **Schema goldens** assert generated JSON Schemas equal the committed files, so the wire contract cannot drift silently.
- **Renderer round-trip** asserts `parse(render(frame)) == project(frame)`, where `project` declares the subset of a frame the plain transcript commits to paper. The round trip is against the projection, not the whole frame: a reviewable transcript cannot carry the command grammar, and lossless transport is the JSONL frontend's job.
- **Reviewed golden transcripts**, a handful per frontend, updated only by humans.

The core suite is plain pytest and must run standalone, without TermVerify installed.

## The boundary

Engine code never imports `termverify`, and the shipped package carries no runtime dependency on it (ADR-001). The adapter consumes only `glyphwright.api` and the published wire schemas, never engine internals. Independence is enforced mechanically, not by discipline: an import-linter contract forbids `glyphwright.* → termverify.*`, and a dedicated CI job runs the core suite in a bare environment without TermVerify present.

ADR-001 binds the engine and the distribution — not the test tree.

| Settled: the engine side | Open: the adapter side (`0003` §20.5) |
| --- | --- |
| Engine, frontends, content packs | Producer-side adapter over `glyphwright.api` |
| Unit and property tests, no TermVerify | Adapter conformance suite |
| Determinism tests | Differential tests across adapter flavors |
| Schema-stability goldens | Reviewed golden transcripts |

Whether the right-hand column lives in TermVerify's examples or here behind an optional dev-only extra is deliberately undecided, to be settled when the adapter is actually built. Either way the left column must keep passing with TermVerify absent.

## Adapter flavors

1. **Direct (in-process)**: import `glyphwright.api`, feed commands, read frames. Fast properties, replay, shrinking.
2. **JSONL subprocess**: speak JSONL over stdio to `glyphwright play --frontend jsonl --harness`. Process isolation with full semantic observations and no ANSI parsing. The expected workhorse.
3. **PTY**: drive the TUI or plain frontend under a pseudoconsole. Production-interaction evidence.

## Determinism and baselines

A run is fully determined by `(engine version, content pack hash, seed, command sequence)`, and the canonical transcript is `(fingerprint, seed, [commands])`. Every session begins with a header carrying the run fingerprint, so engine or content changes invalidate stale baselines rather than passing against different data. Failure shrinking reduces to command-list deletion plus replay.

Randomness is injected and seeded, not absent; ambient entropy, wall-clock time, locale dependence, and terminal-size dependence are what the core excludes. Golden changes require human-readable diffs and explicit review. Adapter and engine drift independently by design; schema tags plus a compatibility matrix manage the skew.
