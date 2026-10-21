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

- [x] Plan, dev dependencies, CLI entry point
- [x] `Rng`
- [x] World (space, grid, entities) and the kernel (commands, events, state)
- [x] `step` (K1) and the exploration mode
- [x] `ContentPack` and the reference village (L1, L2)
- [x] `Engine` API, wire encoding, run fingerprint (K9)
- [x] Schemas (H1, H10) and decision 0002 for the schema tags
- [x] Plain and JSONL frontends, meta channel, CLI (H6, H7), golden transcript
- [x] Property tests (T1, T4, T8) and the enforcing tests for the invariants
- [x] Kernel knowledge page, `AGENTS.md` routes, README quickstart
- [ ] Owner review of the S1 pull request
- [ ] Tag `s1`; move this plan to `docs/plans/completed/`

## Setup log

**Added, because S1's content needs it:**

- `docs/knowledge/` with its index and the kernel page, the first subsystem
  page. Its last section is the checklist for adding an event or a command,
  because that change touches six files.
- An `AGENTS.md` route to the kernel page, and the regeneration commands for
  the two new derived views: the wire schemas and the golden transcript.
- `schemas/`, generated and committed, with a test that fails when the
  encoders and the committed files disagree.
- Decision 0002 on schema versioning, because every later slice bumps a tag.
- A README quickstart, replacing the "no engine yet" notice.

**Deliberately not added yet:**

- **No skills.** Porting a slice has now been done once; the brief's
  candidates (play a session, author a pack) need S2's content first.
- **No `commands` or `content-packs` knowledge pages.** The kernel page covers
  S1's three commands; the command reference is generated in S3.
- **No `--pack`, `--record`, or `--replay`** in the CLI: S2 and S5.

## Decisions

- **A minimal `ContentPack` comes forward from S2**, so `Engine.new(pack,
  seed)` and the run fingerprint have their final shape from S1 on. S2 adds
  the TOML loader behind it.
- **Wire schema tags restart at version 1** (decision 0002).
- **The plain delimiter is ASCII:** `== turn N | mode | area ==`. v0 used a
  middle dot while its docstring promised ASCII; on Windows pipes that byte
  would differ from the other systems. The CLI also forces UTF-8 stdio with
  Unix newlines, because content glyphs may be non-ASCII.
- **`jsonschema` is a dev-only dependency** for validating real output (H10).
  The engine keeps no runtime dependencies.
- **Invariant tests name their invariant**, in `tests/test_invariants.py`,
  so each `AGENTS.md` invariant points at what enforces it.
- **`WorldState.exits_from` stays** as the one movement-graph accessor, so a
  later exit source such as a portal reaches every mover at once.

## Surprises

- **v0's bootstrap commit `02ebe75` was almost exactly S1**, which made it a
  good cross-check for the cut.
- **H6 was wider than the register said.** A line like `move <byte 0xFF>` parses as a
  valid move, so the engine's own rejection echoed the raw byte without
  passing through the JSONL escape. Every frontend now sanitizes each input
  line as it reads it, before anything parses it.
- **The pack-id pin changed**, as expected: v2's `Entity` has fewer
  components than v0's. The pin is re-pinned in this slice.
