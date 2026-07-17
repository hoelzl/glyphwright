---
type: concept
title: Product vision
description: Why GlyphWright is a terminal-first, agent-drivable RPG engine and a reference application under test for TermVerify.
tags: [product, rpg, determinism, terminal, termverify]
---

# Product vision

Authoritative source: `docs/agent/design/0003-glyphwright-design.md` §1–§2.

GlyphWright is a turn-based RPG engine in the tradition of RPG Maker and the Neverwinter Nights toolset: worlds are authored in a grid/tile or room-based format and played through characters, items and inventory, turn-based battles, stats and abilities, and embedded turn-based minigames. Tile/grid structure is a semantic modeling tool, not a mandate that every presentation look like a tile map.

Its distinguishing constraint is that it is **terminal-first and agent-drivable**. An autonomous agent must be able to play, test, and extend GlyphWright games through [TermVerify](https://github.com/hoelzl/termverify)'s verification pipeline, using both a direct semantic adapter and real PTY-driven interaction. GlyphWright is deliberately not a TermVerify component: it is an independent application demonstrating what a well-behaved, verifiable terminal application looks like, and thereby exercising TermVerify's claim of being harness-neutral.

## Goals

1. A complete, small RPG engine: exploration, NPCs, dialogue, items/inventory, turn-based battle, stats/abilities/perks, turn-based minigames.
2. Two spatial geometries behind one abstraction — grid/tile worlds and room-graph worlds — mixable within a single game.
3. Determinism as a contract: a run is fully determined by `(engine version, content pack hash, seed, command sequence)`.
4. Semantic evidence first: structured frames and typed events are the primary observations; rendered text is derived.
5. Three frontends over one core: plain line-oriented REPL, JSONL structured stream, full-screen TUI.
6. A stable, versioned public API and wire format an external adapter can consume without touching engine internals.
7. Content-driven games: worlds, entities, items, abilities, and dialogue defined in data files, validated against schemas.

## Non-goals

Permanent, because they contradict what GlyphWright is: real-time gameplay, since the engine is turn-based to its foundations and turn count *is* time; a general-purpose scripting language for game logic, since effect primitives are implemented in Python and content composes them; multiplayer; and importing `termverify` from engine code, ever — which binds the shipped package, and leaves open whether test tooling here may use it (`0003` §20.5).

## Deferred

Graphical rendering, animation timing, and audio are out of scope for now but are **not** ruled out. The world model is deliberately presentation-independent, so a graphical frontend consuming the same frames and events could be added later. These are deferrals: they must grow from the deterministic core rather than bypass it, and adding one is a scope decision for the owner rather than something to refuse.

## Success

The product succeeds when adding a renderer does not change game rules, and when strengthening verification does not require a special agent vendor or proprietary runtime.
