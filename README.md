# GlyphWright

A deterministic, terminal-first turn-based RPG engine, drivable by people and autonomous agents alike.

GlyphWright is an RPG engine in the tradition of RPG Maker and the Neverwinter Nights toolset: worlds are authored in a grid/tile or room-based format and played through characters, items and inventory, turn-based battles, stats and abilities, and embedded minigames. It separates world semantics from presentation — a state plus a command produces a new immutable state and ordered semantic events — so that structured evidence, not screen-scraped text, is the primary observation.

The current vertical slice is the walking skeleton: a pure `step` over immutable state, typed events, a seeded PCG64 stream, a grid world behind the `Space` protocol, semantic frames, plain and JSONL frontends, the `glyphwright.api` public surface, and committed wire schemas.

## Why

Visual RPG editors and 3D clients can still be backed by tile-like world structure. GlyphWright makes that structure authoritative without requiring any particular renderer. The terminal representation is a first-class interaction surface: it keeps world behavior cheap to inspect, script, replay, and verify.

GlyphWright is also a reference application under test for [TermVerify](https://github.com/hoelzl/termverify) — an autonomous agent should be able to play, test, and extend its games through both a direct semantic adapter and real PTY-driven interaction. It is deliberately *not* a TermVerify component and never imports it; that independence is what makes it a real test of TermVerify's harness-neutrality.

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/) and Python 3.12–3.14.

```bash
uv --no-config sync --all-groups --locked
uv --no-config run glyphwright
```

The session accepts `move <north|east|south|west>`, `look`, `wait`, `help`, and `quit`. Each turn prints a transcript block anchored by `== turn N · mode · area ==`.

Run a reproducible scripted session without a PTY:

```bash
printf 'move east
move south
quit
' | uv --no-config run glyphwright
```

Agents and out-of-process verification should prefer the JSONL frontend, which emits one `SemanticFrame` per line and needs no ANSI parsing:

```bash
printf 'move east
quit
' | uv --no-config run glyphwright --frontend jsonl --harness
```

A run is fully determined by `(engine version, content pack hash, seed, command sequence)`. The seed is explicit (`--seed`) and recorded in the session header, so any transcript names exactly what produced it.

## Development

```bash
uv --no-config run pytest --cov --cov-report=term-missing
uv --no-config run ruff check .
uv --no-config run ruff format --check .
uv --no-config run mypy src tests
uv --no-config build
```

See [`AGENTS.md`](AGENTS.md), [`CONTRIBUTING.md`](CONTRIBUTING.md), and the [knowledge index](docs/knowledge/index.md).

## Status and scope

GlyphWright is pre-alpha. Items and stats, battle, room-graph areas and portals, a TUI, dialogue, and minigames are all planned but not built yet, and must grow from the deterministic core rather than bypass it. The design document below sets the order.

Deferred, but not ruled out: graphical rendering, animation timing, and audio. The world model is deliberately presentation-independent, so a graphical frontend consuming the same frames and events could be added later.

Permanently out of scope, because they contradict what GlyphWright is: real-time gameplay (the engine is turn-based to its foundations — turn count *is* time), a general-purpose scripting language for game logic, multiplayer, and any runtime dependency on TermVerify — the engine must always run with TermVerify absent.

## Design

[`docs/agent/design/0003-glyphwright-design.md`](docs/agent/design/0003-glyphwright-design.md) is the authoritative statement of GlyphWright's purpose, architecture, and implementation plan.

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
