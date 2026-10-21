# GlyphWright v2 — Project brief

What GlyphWright v2 is, who it serves, what the core must do, and the slices
that build it. Read it before you plan or start a slice.

## Contents

- [Decisions already taken](#decisions-already-taken)
- [What it is](#what-it-is)
- [Who it is for](#who-it-is-for)
- [Jobs the core must do](#jobs-the-core-must-do)
- [Core scope](#core-scope)
- ["Core done": the usability gate](#core-done-the-usability-gate)
- [Information architecture from day 0](#information-architecture-from-day-0)
- [Slices](#slices)
- [Capturing teaching material](#capturing-teaching-material)

## Decisions already taken

Taken by the owner on 2026-10-20, before the repository existed.

- **Fresh repository.** Public, Apache-2.0, named `hoelzl/glyphwright`. The
  first attempt is archived as
  [`hoelzl/glyphwright-v0`](https://github.com/hoelzl/glyphwright-v0).
- **Core first.** A small core that agents and humans can use comes first.
  Each later feature is added only when real use of the core asks for it.
- **No termverify.** GlyphWright v2 neither depends on termverify nor
  positions itself as its reference application.
- **Python 3.12–3.14.** Nothing the core needs requires a newer version;
  newer typing features come from `typing_extensions`.
- **PyPI after S5.** Until then the project installs from a clone.
- **Plain `uv`.** A `[tool.uv]` table in `pyproject.toml` keeps uv from
  applying a parent folder's uv settings.
- **One instruction file and one skills folder for all agent harnesses**:
  [decision 0001](decisions/0001-agent-harness-layout.md).
- **Day 0 follows the information-architecture rules** taught in the
  course deck that uses this repository as its example. Day 0 starts with an
  initial set of instructions: the invariants and the lessons of v0 and
  termverify. After that, rules follow observed mistakes.

## What it is

A deterministic, turn-based RPG engine. You author worlds as data, and both
people and coding agents can play them.

A game step is a pure function, `step(state, command, rng) → (state, events)`.
Every observation is a structured frame, and rendered text is derived from it.
The structured frames, together with replay of recorded sessions, make the
engine easy for an agent to drive, test, and extend without screen scraping.

## Who it is for

The repository serves three audiences. Each audience gets its own path through
the documentation.

| Audience | Needs |
|---|---|
| **Engine developers** (human or agent) | Kernel invariants, the module map, how to add a command, a component, or an effect safely, and the gates to run |
| **Content authors** | The content-pack format, validation diagnostics, the reference world, and how to playtest a pack |
| **Agents playing or verifying** | The JSONL protocol, the command grammar, `:query`, record/replay, and the determinism contract |

A fourth audience reads the repository rather than working in it: course
participants studying it as an example of information architecture for agents.
They are why the structure must be legible, not merely correct.

## Jobs the core must do

1. **Author and play a small world.** Load a TOML content pack, explore a grid
   area, pick up and use items, and fight a menu battle. Play it as plain text
   or as a JSONL stream.
2. **Let an agent verify behavior.** Record a session, replay it, and get an
   exact verdict on divergence. Ask `:query … --explain` why a stat has its
   value.
3. **Extend safely.** Add an item, an enemy, or a stat modifier by following a
   skill, with gates that catch broken invariants.

## Core scope

The scope is ported from
[v0 at commit `3ecc396`](https://github.com/hoelzl/glyphwright-v0/tree/3ecc396)
slice by slice. It is not rewritten from scratch. The invariants that bind all
of it are in [`AGENTS.md`](../AGENTS.md#invariants).

| In the core | Source in v0 (`src/glyphwright/…`) |
|---|---|
| Kernel: pure `step`, typed events folded into state, seeded PCG64 stream in state, snapshots | `kernel/` |
| One geometry: `GridSpace` behind the `Space` protocol | `world/` (grid only) |
| Exploration mode: `move`, `look`, `wait`, with typed rejections and the command grammar | `modes/exploration.py` |
| Items and stats: `take`/`use`/`equip`, stat pipeline with per-modifier provenance | `world/entities.py`, `effects/stats.py` |
| Menu battle: mode stack, rolled initiative, `attack`/`use`/`flee`, AI turns inside `step` | `modes/battle.py`, `kernel/scheduler.py` |
| TOML content packs with located load diagnostics; a reduced reference world | `content/` |
| Session recording and replay, with determinism fingerprints | `harness/recording.py`, `harness/fingerprint.py` |
| Introspection meta-channel: `:query --explain`, `:seed`, `:frame` | `harness/query.py` |
| Plain and JSONL frontends; the `glyphwright.api` public surface; committed wire schemas | `frontends/plain.py`, `frontends/jsonl.py`, `api.py`, `schemas/` |

**Deferred until real use asks for them:** rooms and portals, abilities and
statuses, hooks and perks, resources, field of view and the tactics arena,
dialogue, the lockpicking minigame, and the full-screen TUI and the GUI.

**Dropped:** the UE5 presentation path and its oracle and drift-audit
machinery.

### Known v0 defects to fix during the port

v0's
[adversarial-review register](https://github.com/hoelzl/glyphwright-v0/blob/3ecc396/docs/agent/handovers/adversarial-review-remediation.md)
lists 64 findings. Fix the ones that fall inside the core as part of the slice
that ports the affected code, and record each fix in that slice's plan.
Examples:

- **K1:** the rng comparison in `step`.
- **K5:** `Healed` has no lower clamp and no death check.
- **L1:** duplicate entity ids are not detected.
- **L2:** hp bounds are not validated.
- **H2:** the version never changes, so replay checks are meaningless.
- **H4, H8:** recording headers are not schema-validated, and a UTF-8 BOM
  breaks replay.
- **H6, H7:** JSONL echoes invalid UTF-8, and its error hints are incomplete.

Findings in deferred or dropped areas stay in v0. Some confirmed core bugs may
also be kept, deliberately, at the pinned v0 commit as debugging-workshop
material for the course.

## "Core done": the usability gate

The core is done when all of the following hold on a clean checkout. No
feature beyond the core starts before then.

1. **Human:** the README quickstart plays the reference world within five
   minutes on Windows, macOS, and Linux.
2. **Agent, using only `AGENTS.md` and the skills:**
   - authors a two-area content pack and gets located diagnostics for a
     broken one;
   - plays it through JSONL;
   - records a session and replays it to an exact verdict;
   - adds a new item kind with a test, and all gates pass.
3. **CI** passes on Windows, macOS, and Linux.

## Information architecture from day 0

The structure starts minimal: a document or folder exists only once there is
content for it. The rules are in
[`CONTRIBUTING.md`](../CONTRIBUTING.md#documentation-rules); this is the
intended shape.

- **Tier 1, always loaded:** `AGENTS.md`, a map within a gated size budget. It
  points to where knowledge lives rather than describing the folder tree.
- **Tier 2, on demand:**
  - [`docs/README.md`](README.md), the documentation map;
  - `docs/knowledge/`, one page per subsystem or contract (kernel, content
    packs, commands, replay and determinism, verification), each added by the
    slice that ports that subsystem;
  - `docs/plans/active/` and `docs/plans/completed/`, one plan per slice;
  - `docs/decisions/`, short decision records;
  - skills in `.agents/skills/`, written once a procedure has been done twice.
    Likely candidates: play-a-session, author-a-pack, add-an-item, and
    pin-behavior-with-a-replay.
- **Tier 3, self-reporting:** one check command that runs every gate, with
  error messages that say how to fix the problem; later `glyphwright --help`,
  `:query`, and the grammar enumeration in every frame.
- **Tier 4, generated and checked for staleness:** the documentation indexes
  and the Claude Code command stubs from day 0; the command-grammar reference
  and the content-pack schema reference once the code exists.

## Slices

| Slice | Delivers | Ends with |
|---|---|---|
| **S0 — day 0** | Repository skeleton, uv project, gates, CI on three operating systems, the `AGENTS.md` map, the documentation map, the stub generator, this brief | The documentation rules pass; owner review before any code is ported |
| **S1 — walking skeleton** | Kernel, `GridSpace`, exploration, plain and JSONL frontends, `api`, schemas | A playable hard-coded area; kernel knowledge page |
| **S2 — content packs** | TOML loader with located diagnostics; reduced reference world | Play from a pack; content-pack knowledge page; first author-facing docs |
| **S3 — items and stats** | Inventory, stat pipeline with provenance, `:query --explain` | Generated command reference |
| **S4 — menu battle** | Mode stack, scheduler, battle | The core gameplay loop is complete |
| **S5 — record and replay** | Recording, replay, fingerprints, determinism contract | The usability gate is run and recorded; first course tag |

Every slice is a vertical increment that a user or agent can try. Each one
updates `AGENTS.md` and the documentation map only where its new content
requires it. The working rules for slices are in
[`CONTRIBUTING.md`](../CONTRIBUTING.md#working-rules).

## Capturing teaching material

A course deck on information architecture for agents is written from this
project's history. The project therefore keeps:

- **Tags:** `day-0`, then one per slice, plus a course tag after S5.
- **Commit history:** meaningful, one concern per commit, so that diffs of
  `AGENTS.md` and of the documentation map read as a story.
- **A setup log:** in each slice's plan, a few lines on what structure was
  added, what was deliberately *not* added, and why.
