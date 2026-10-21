# S1 — Walking skeleton

The plan and record of slice S1: the kernel, one grid, exploration, the plain
and JSONL frontends, the public API, and the wire schemas, ported from v0 and
playable in a hard-coded area. Read it to continue S1 or to see what was cut
from v0 and why.

## Contents

- [Goal](#goal)
- [Scope](#scope)
- [Defects fixed in the port](#defects-fixed-in-the-port)
- [Progress](#progress)
- [Setup log](#setup-log)
- [Decisions](#decisions)
- [Surprises](#surprises)

## Goal

A person or an agent can play a small hard-coded grid area: `move`, `look`,
and `wait`, as plain text or as a JSONL stream, with typed rejections and a
command grammar in every frame. The kernel's invariants are enforced by tests,
and a knowledge page explains the kernel.

## Scope

Ported from
[v0 at `3ecc396`](https://github.com/hoelzl/glyphwright-v0/tree/3ecc396), cut
to what exploration needs. v0's first commit, `02ebe75`, had almost exactly
this shape and serves as the cross-check.

| Area | S1 keeps | Later |
|---|---|---|
| Kernel | `Rng` (PCG64), `step`, `Move`/`Look`/`Wait`, `Moved`/`MoveBlocked`/`TurnAdvanced`, `WorldState` with a mode stack | items (S3); scheduler, battle, flags (S4) |
| World | `Space` protocol, `GridSpace` without field of view, `Entity` with position, actor, blocker, renderable | inventory, equipment, stats (S3); AI (S4) |
| Modes | the mode protocol and exploration | battle (S4); dialogue, lockpick (deferred) |
| Frames and wire | `SemanticFrame` with a grid view; JSONL encoding; schemas at version 1 | menu view (S4) |
| Content | a minimal `ContentPack` and a code-built reference area | TOML packs (S2) |
| Harness | run fingerprint, `:seed` and `:frame` | `:query` (S3); record and replay (S5) |
| Frontends | plain, JSONL, and the CLI | `--pack` (S2); `--record`, `--replay` (S5) |

## Defects fixed in the port

From v0's
[adversarial-review register](https://github.com/hoelzl/glyphwright-v0/blob/3ecc396/docs/agent/handovers/adversarial-review-remediation.md),
the findings in code that S1 ports:

| ID | Defect | Fix |
|---|---|---|
| K1 | `step` compares the rng against the wrong cursor | compare against the argument; failing test first |
| K9 | verb arity and domain count can disagree | test that pins them for the exploration grammar |
| L1 | duplicate entity ids are not detected | check in `ContentPack` |
| L2 | hp bounds are not validated | check `0 <= hp <= max_hp` in `ContentPack` |
| H1 | the event schema is not discriminated | one schema per event type |
| H6 | JSONL echoes invalid UTF-8 | escape it; force UTF-8 stdio |
| H7 | JSONL error hints are hardcoded and incomplete | build them from the frame's grammar |
| H10 | the schema test does not recurse | validate nested schemas fully |
| T1, T4 | property tests check too little, too late | whole-state fold check after every step |

## Progress

- [ ] Plan, dev dependencies, CLI entry point
- [ ] `Rng`
- [ ] World: space, grid, entities
- [ ] Kernel: commands, events, state
- [ ] Frames and the exploration mode
- [ ] `step` (K1)
- [ ] `ContentPack` and the reference area (L1, L2)
- [ ] Wire encoding and run fingerprint
- [ ] `Engine` API (K9)
- [ ] Schemas (H1, H10) and decision record for the schema tags
- [ ] Plain frontend and golden transcript
- [ ] Meta channel and JSONL frontend (H6, H7)
- [ ] CLI
- [ ] Property tests (T1, T4) and the no-ambient-I/O test
- [ ] Kernel knowledge page, docs map, `AGENTS.md` route, README quickstart

## Setup log

Filled in as the slice proceeds.

## Decisions

- **A minimal `ContentPack` comes forward from S2**, so `Engine.new(pack,
  seed)` and the run fingerprint have their final shape from S1 on. S2 adds
  the TOML loader behind it.
- **Wire schema tags restart at version 1.** S1's frames and events differ
  from v0's, so continuing v0's numbers would suggest a compatibility that
  does not exist. Recorded as a decision.

## Surprises

None yet.
