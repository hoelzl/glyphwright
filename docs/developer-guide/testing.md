# Testing and verification

GlyphWright verifies the semantic engine before presentation. During TDD, run one named test and observe the intended failure; after it passes, run the containing file, then the full gate before completion.

The authoritative strategy is `docs/agent/design/0003-glyphwright-design.md` §17; `docs/knowledge/verification-model.md` summarizes the model. This page covers how to work with the suite.

## Layers

1. Unit tests cover parsing, transitions, rendering data, and individual rules.
2. Property tests walk commands generated from the frame's `CommandGrammar` and assert invariants as the state model grows.
3. Determinism tests assert identical `(pack, seed, commands)` yields identical frame and event sequences, and that replay-from-log equals snapshot/restore.
4. Purity tests assert `step` does not mutate its input state.
5. Schema goldens assert generated JSON Schemas equal the committed files.
6. Renderer round-trip asserts `parse(render(frame)) == project(frame)` — the declared transcript projection, not the whole frame; lossless frame transport is the JSONL frontend's job.
7. Terminal e2e tests drive the installed line-oriented CLI through subprocess pipes; PTY tests prove interactive behavior.
8. Graphical renderers, when introduced, consume frames and do not become correctness oracles.

Layers 3–6 arrive with the machinery they test (`0003` §18); the bootstrap suite covers 1, 7, and part of 2.

Tests marked `e2e` cross a process or terminal boundary. Keep ordinary semantic tests fast and platform-independent. No test may silently update a golden file.

## Independence

The core suite is plain pytest and must pass with TermVerify **not** installed — CI enforces this in a bare environment, and an import-linter contract forbids `glyphwright.* → termverify.*`. Never import `termverify` from engine code, and never give the shipped package a runtime dependency on it.

Whether adapter and differential tests live here (behind an optional dev-only extra) or in TermVerify's examples is an open question, to be decided when the adapter is built (`0003` §20.5). If they do land here, they must be excluded from the bare CI job so the core suite stays independent.

## Determinism checklist

A verified run must make command order, initial world, content-pack identity, seed, and renderer format explicit. Randomness is permitted only through the injected seeded stream whose cursor lives in world state; ambient time, entropy, locale, terminal size, filesystem, and network access must not reach the kernel, and anything affecting behavior must be captured in replay evidence.
