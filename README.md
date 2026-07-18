# GlyphWright

A deterministic, terminal-first turn-based RPG engine, drivable by people and autonomous agents alike.

GlyphWright is an RPG engine in the tradition of RPG Maker and the Neverwinter Nights toolset: worlds are authored in a grid/tile or room-based format and played through characters, items and inventory, turn-based battles, stats and abilities, and embedded minigames. It separates world semantics from presentation — a state plus a command produces a new immutable state and ordered semantic events — so that structured evidence, not screen-scraped text, is the primary observation.

All six designed slices are in place — dialogue and a minigame completing the set: a pure `step` over immutable state, typed events, a seeded PCG64 stream, grid *and* room-graph worlds behind one `Space` protocol — the reference world mixes a village grid with an IF-style inn interior through a portal door — inventory (`take`/`use`/`equip`), a stat pipeline with per-modifier provenance, melee skirmishes and formal menu battles (a real mode stack with rolled initiative, `attack`/`use`/`flee`, victory and defeat outcomes) whose AI turns run inside the same `step`, content-authored dialogue trees (`talk`/`choose`) and a lockpicking minigame (`open`/`pick`) as ordinary modes, abilities and timed statuses composed from effect primitives (`cast firebolt at goblin-1`), worlds authored as TOML content packs (`--pack <dir>`, with located load diagnostics), pack-level field of view and grid-arena tactics battles, verified session recording and replay (`--record`/`--replay`), an introspection meta-channel (`:query player.stats.atk --explain`), semantic frames, plain, JSONL, and full-screen TUI frontends, the `glyphwright.api` public surface, and committed wire schemas.

## Why

Visual RPG editors and 3D clients can still be backed by tile-like world structure. GlyphWright makes that structure authoritative without requiring any particular renderer. The terminal representation is a first-class interaction surface: it keeps world behavior cheap to inspect, script, replay, and verify.

GlyphWright is also a reference application under test for [TermVerify](https://github.com/hoelzl/termverify) — an autonomous agent should be able to play, test, and extend its games through both a direct semantic adapter and real PTY-driven interaction. It is deliberately *not* a TermVerify component and never imports it; that independence is what makes it a real test of TermVerify's harness-neutrality.

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/) and Python 3.12–3.14.

```bash
uv --no-config sync --all-groups --locked
uv --no-config run glyphwright
```

The session accepts `move <exit>`, `look`, `wait`, `take <item>`, `use <item>`, `equip <item>`, `attack <target>`, `talk <npc>`, `open <container>`, `cast <ability> at <target>`, `choose <n>` (in dialogue), `pick`/`abort` (at a lock), `flee` (in battle), `help`, and `quit`. Each turn prints a transcript block anchored by `== turn N · mode · area ==`. The frame's command grammar always names exactly what is valid right now.

With `--harness`, a namespaced meta-channel is available beside the game commands — the engine's oracle interface, which never advances the turn:

```text
:query player.hp                 -> player.hp = [17, 20]
:query player.stats.atk --explain
:seed
:frame [--json]
```

Run a reproducible scripted session without a PTY:

```bash
printf 'move east
move south
quit
' | uv --no-config run glyphwright
```

A full-screen session (hand-rolled ANSI, arrows/hjkl plus hotkeys, `;` for a typed command bar, `:` for the meta bar, `q` to quit):

```bash
uv --no-config run glyphwright --frontend tui --harness
```

A graphical session (a window, same keys as the TUI; needs the optional `gui` extra — `pip install "glyphwright[gui]"`, or `uv --no-config sync --all-groups --all-extras` in a checkout). Exploration renders in the window; battle, dialogue, and lockpicking still direct you to the TUI for now:

```bash
uv --no-config run glyphwright --frontend gui
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

GlyphWright is pre-alpha. Statuses now carry event-triggered hooks (poison ticks, wounded-threshold reactions), perks join the stat pipeline as permanent statuses, and hostiles cast abilities when out of melee reach. Abilities now cost mana from a per-actor pool (affordability gates the grammar and the AI alike). Progression mechanisms and richer hook targeting are planned but not built yet, and must grow from the deterministic core rather than bypass it. The design documents below set the order.

Graphical rendering has begun: a pygame-ce window frontend (optional `gui` extra) plays exploration today and grows toward full parity per design `0011`; the engine itself stays presentation-independent and dependency-free. Animation timing and audio remain deferred, but not ruled out.

Permanently out of scope, because they contradict what GlyphWright is: real-time gameplay (the engine is turn-based to its foundations — turn count *is* time), a general-purpose scripting language for game logic, multiplayer, and any runtime dependency on TermVerify — the engine must always run with TermVerify absent.

## Design

[`docs/agent/design/0003-glyphwright-design.md`](docs/agent/design/0003-glyphwright-design.md) is the authoritative statement of GlyphWright's purpose, architecture, and implementation plan.

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
