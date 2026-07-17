---
type: reference
title: Terminology
description: Stable terms used in GlyphWright code and design documents.
tags: [terminology, domain-model]
---

# Terminology

Authoritative source: `docs/agent/design/0003-glyphwright-design.md`. These are the terms the
design specifies; code that uses different names is wrong and should be renamed.

## Core

- **World state**: the immutable state required to resolve a turn — entity table, area table, mode stack, scheduler queue, RNG cursor, turn counter, flags, and message-log cursor.
- **Command**: presentation-independent player intent, such as `move north` or `attack goblin-1 with dagger`. Never a keystroke.
- **Step**: the pure transition `step(state, command, rng) -> (next_state, events)`. All engine behavior, including NPC turns, happens inside it.
- **Event**: ordered typed semantic fact emitted by a step. The successor state is the fold of events over the prior state; events are the engine's primary evidence.
- **Step result**: what the API returns for one command — frame plus events, or a typed rejection.
- **Rejection**: typed `Rejected(reason, hint)` for an invalid command. Not an exception, so agents get machine-readable feedback and fuzzing can distinguish "rejected as designed" from "engine fault".
- **Outcome**: the victory/defeat payload carried by `ModePopped` and consumed by the mode beneath. Not a general transition result.
- **Turn**: the engine's only clock. There is no wall clock in the kernel.
- **Seed**: the explicit value constructing the PCG64 stream; its cursor lives in world state so replay resumes exactly.
- **Scheduler**: the single turn scheduler serving both exploration and battle, granting turns to AI actors after the player's command resolves.

## Space and content

- **Space**: the protocol both geometries implement, exposing positions, exits, passability, occupants, and observation.
- **Grid space**: tile geometry with `(x, y)` or `(x, y, layer)` positions; `x` increases east, `y` increases south. Exits derive from adjacency; layer transitions are explicit exits.
- **Room graph space**: IF-style geometry with opaque room IDs and authored exits.
- **Area**: one space of one kind; a world is a set of areas.
- **Portal**: paired exit entities connecting areas, including across space kinds.
- **Position identity**: stable semantic identifier such as `village:7,3` or `cellar:wine-room`. Never a screen coordinate.
- **Tile**: terrain at one grid position.
- **Entity**: a stable, human-meaningful ID plus a bag of components.
- **Content pack**: a directory of TOML files defining worlds, entities, items, abilities, and dialogue, validated against published schemas at load.
- **Pack ID**: the hash of a content pack; part of the run fingerprint, so content changes invalidate baselines.

## Rules

- **Effect primitive**: a Python-implemented vocabulary item (`deal_damage`, `apply_status`, `heal`, …) that content composes by name. There is no scripting language.
- **Ability**: data — requirements, cost, targeting spec, and an ordered list of effect primitives.
- **Status**: a bundle of stat modifiers plus event-triggered hooks, with a duration in turns.
- **Perk**: a permanent status acquired through progression.
- **Provenance**: the source, duration, and magnitude carried by every stat modifier, making a derivation assertable.

## Presentation and verification

- **Mode**: a pushdown-automaton state (exploration, battle, dialogue, menu, minigame) implementing `available_commands`, `handle`, and `view`. Mode transitions are events.
- **Semantic frame**: the canonical observation after a step — turn, mode, viewport, actors, message delta, prompt, and command grammar. Pure data.
- **Command grammar**: the currently valid verbs and argument domains, carried in every frame; the generator for property-based fuzzing.
- **Renderer**: pure projection of a frame into a presentation. Never mutates the world.
- **Frontend**: plain line REPL, JSONL stream, or TUI. All are pure functions over frames.
- **Terminal session**: the production line-oriented adapter mapping text input to commands and rendering results.
- **Meta-channel**: the `:`-prefixed introspection vocabulary gated by `--harness`; queries never advance the turn.
- **Run fingerprint**: engine version, pack ID, seed, and turn — recorded in every session header.
- **Replay**: the canonical transcript `(fingerprint, seed, [commands])`, sufficient to reproduce and compare a run.
- **Snapshot**: an opaque, serializable world state; free, because state is immutable.
