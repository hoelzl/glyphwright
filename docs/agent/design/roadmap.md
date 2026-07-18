# Early roadmap

The authoritative implementation plan is `0003-glyphwright-design.md` §18. This page tracks
progress against it and must not introduce an ordering of its own.

## Slice order (`0003` §18)

Vertical slices, ordered to exercise the verification boundary as early as possible. The TUI is deliberately fifth: the engine must be fully verifiable before a single ANSI escape exists.

| # | Slice | State |
|---|---|---|
| 1 | **Walking skeleton.** Kernel (`step`, events, seeded RNG, snapshots), `GridSpace`, `move`/`look`, plain + JSONL frontends, `glyphwright.api`, published schemas. | Done |
| 2 | **Items and stats.** Inventory, `take`/`use`/`equip`, stat pipeline with provenance, `:query --explain`. | Done |
| 3 | **Battle.** Menu battle first, forcing the mode stack and shared initiative scheduler into existence; tactics arena reusing `GridSpace` as a follow-up. | Done for menu battle (3A exploration combat + 3B menu battle mode); tactics arena deferred until FOV/visibility (§20.3) |
| 4 | **Rooms and portals.** `RoomGraphSpace`, plus a portal between a grid area and a room area in the reference pack. | Done |
| 5 | **TUI.** Full-screen frontend; differential tests against plain. | Done — hand-rolled ANSI (`0003` §20.1 resolved). In-repo, a projection-consistency test asserts every fact the plain transcript commits to also appears on the TUI screen; PTY-driven differential runs remain TermVerify-side (§20.5) |
| 6 | **Dialogue and one minigame.** Dialogue trees, plus a lockpicking or card minigame proving the mode interface is general. | Done |

## Slice 1 scope

- Kernel: `step(state, command, rng)`, typed events with fold semantics, seeded PCG64 stream with its cursor in world state, snapshots (`0003` §5).
- `Space` protocol with `GridSpace` as its first implementation (`0003` §7.1–§7.2).
- Area-qualified position identifiers (`village:7,3`) in events, frames, and queries (`0003` §7.5).
- Semantic commands `move <exit-token>` and `look`, with typed rejections and `CommandGrammar` enumeration (`0003` §6).
- `SemanticFrame` as the canonical observation (`0003` §11).
- Plain and JSONL frontends as pure functions over frames (`0003` §12).
- The `glyphwright.api` public surface (`0003` §14).
- Generated, committed, golden-tested wire schemas with tags and session fingerprints (`0003` §15).
- Determinism, purity, schema-golden, and renderer round-trip tests (`0003` §17).

Deferred within slice 1: the meta-channel beyond what the API needs, FOV/visibility (`0003` §20.3), and the mode stack beyond a single exploration mode.

TermVerify side, out of this repository's scope for now: the direct adapter and one PTY golden against the plain frontend (`0003` §20.5 decides where that lives).

## Slice 2 scope (shipped)

- Inventory as components: `Item`, `Consumable`, `Equippable`, `Inventory`, `Equipment`
  (`0003` §8.1); `take`/`use`/`equip` with grammar-drawn argument domains (`0003` §6).
- Events `ItemAcquired`, `ItemUsed`, `ItemEquipped`, `Healed`, folded like every other
  state change (`0003` §5.3).
- Stat pipeline base → additive → multiplicative → clamps with provenance on every
  contribution (`0003` §9.1), equipment as the first modifier source.
- Introspection meta-channel `:query <path> [--explain]`, `:seed`, `:frame [--json]`
  behind `--harness` in both frontends, and `Engine.query` in the public API
  (`0003` §13–§14). `:events --since` and `:save`/`:load` are deferred until a consumer
  needs them.
- `glyphwright.query/1` wire schema; event vocabulary changes bumped the tag to `glyphwright.event/2` (v1 retired before any consumer existed).

## Post-plan slices

| # | Slice | State |
|---|---|---|
| 7 | **Abilities, statuses, effect primitives** (`0004`, scoping `0003` §9.2–§9.3): primitive registry, `cast <ability> at <target>` at arity two, timed statuses in the stat pipeline with provenance. Hooks and perks deferred. | Done |
| 8 | **TOML content packs** (`0005`, scoping `0003` §8.2): stdlib-tomllib loader with located diagnostics, the reference pack itself as packaged TOML, `--pack <dir>`. | Done |
| 9 | **Tactics battle + FOV** (`0006`, scoping `0003` §10.1, §20.3). | Done — 9A FOV, 9B tactics arena (grid battles with placement/homecoming via events, chase-or-strike foes, break-contact flee) |
| 10 | **Status hooks, perks, AI ability use** (`0007`, scoping `0003` §9.3 and `0004` §5's deferrals). | Done — event-triggered hooks (damage_taken/turn_end, hp_below gate, one generation per step), perks as permanent statuses (`PerkGained`, `grant_perk`), hostiles cast when they cannot strike |
| 11 | **Session recording and replay** (`0008`, resolving `0003` §20.2). | Done — replay as the durable format: session header + per-step command lines with SHA-256 event digests, `--record`/`--replay` on the CLI, header-gated compatibility |
| 12 | **Resource pools and ability costs** (`0009`, lifting `0004` §2's deferral). | Done — `Actor.mp`, `Ability.cost` with affordability-as-advertisement, `ManaSpent`/`ManaRestored` (event v9), mana consumables, `mp` in frames (v5) and the oracle |

## Next integration step

`0010-termverify-integration-assessment.md` (2026-07-18) surveys TermVerify's state: the
direct in-process adapter path is feasible now and is the next integration step; the JSONL
subprocess and PTY flavors, and all differential testing, are blocked on TermVerify-side
work listed there as prioritized asks.

## Open questions

`0003` §20 holds the live list: adapter placement (§20.5) is the only question still open. Repository placement (own repository) and the TUI substrate (hand-rolled ANSI) were resolved on 2026-07-17; the snapshot format (replay as the durable format, slice 11) and FOV/visibility (pack-level option, slice 9A) on 2026-07-18.
