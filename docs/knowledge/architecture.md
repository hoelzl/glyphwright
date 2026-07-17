---
type: concept
title: Architecture
description: Layered boundaries around GlyphWright's deterministic kernel, spatial model, mode stack, and frontends.
tags: [architecture, deterministic-core, adapters, modes, frames]
---

# Architecture

Authoritative source: `docs/agent/design/0003-glyphwright-design.md` §4–§15. This page is the
stable summary; the design document wins on any disagreement.

## Layers

Data flows downward as commands and upward as events and frames. Only the topmost layer knows about terminals; only `glyphwright.api` is public.

| Layer | Responsibility |
| --- | --- |
| Terminal frontends | plain REPL, TUI, JSONL |
| Presentation | `SemanticFrame` → renderers |
| Mode stack | exploration, battle, dialogue, menu, minigames |
| Deterministic kernel | `step()`, scheduler, events, seeded RNG, snapshots |
| World model | `Space` protocol, entities, components, content packs |

## The central contract

```python
def step(state: WorldState, command: Command, rng: Rng) -> tuple[WorldState, tuple[Event, ...]]
```

`step` is pure: no I/O, no wall clock, no ambient globals. All engine behavior, including NPC turns triggered by a player command, happens inside it.

`WorldState` is immutable. Every state change is expressed as a typed event, and the successor state is the fold of the event list over the prior state (`apply(state, event) -> state`). Snapshots are therefore free, replay and undo are trivial, and tests can assert that `step` did not mutate its input.

Commands are semantic intents, never keystrokes. Invalid commands are not exceptions: they produce a typed `Rejected(reason, hint)` carried in the `StepResult`, so agents get machine-readable feedback and fuzzing can distinguish "rejected as designed" from "engine fault".

## Determinism

A run is fully determined by `(engine version, content pack hash, seed, command sequence)`.

Time is the turn counter; there is no wall clock in the kernel. Randomness is a seeded PCG64 stream whose cursor is part of `WorldState`, so replay from a snapshot resumes the exact stream. Randomness is *injected and deterministic*, not absent — ambient entropy is what the core excludes. Iteration over entities is in sorted-stable-ID order.

## Spatial model

Grid worlds and room worlds implement one `Space` protocol rather than emulating each other, and `move <exit-token>` is the only movement command everywhere. `GridSpace` derives exits from adjacency and uses `(x, y)` or `(x, y, layer)` positions, with `x` increasing east and `y` increasing south; `RoomGraphSpace` uses opaque room IDs with authored exits. A world is a set of areas, each with its own space kind, connected by portals; one game may combine a grid overworld with room-based interiors.

Positions in events, frames, and queries are stable semantic identifiers — `village:7,3`, `cellar:wine-room` — never screen coordinates. Verification assertions must survive rendering changes.

## Modes and frames

Engine control flow is a pushdown automaton of modes. Exploration sits at the bottom; battle, dialogue, menu/inventory, and minigames push on top. Mode transitions are themselves events, hence replayable and assertable. Battle is an ordinary mode configuring the shared turn scheduler, not a private loop.

After each step the active mode produces a `SemanticFrame`: turn, mode, viewport, visible actors, this turn's message delta, the expected prompt, and the currently valid `CommandGrammar`. Frames are pure data and all frontends are pure functions over frames. Message text is generated from templates over event data, never free-written in handlers.

## Boundaries

Terminal, graphical, editor, filesystem, clock, and network concerns live outside the kernel. Content packs enter through an explicit loading boundary. A renderer consumes frames; it never mutates the world.

`glyphwright.api` is the only supported programmatic entry point, versioned independently of internals; nothing in `kernel/`, `world/`, `modes/`, or `effects/` is public. Engine code never imports `termverify` and the shipped package has no runtime dependency on it (`0003` ADR-001); the producer-side adapter consumes only `glyphwright.api` and the published wire schemas, and where it lives is an open question (`0003` §20.5).
