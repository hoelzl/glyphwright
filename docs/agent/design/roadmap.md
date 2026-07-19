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
| 13 | **Graphical frontend** (`0011`): pygame-ce behind a `glyphwright[gui]` extra, pure `compose(frame) → Scene` core, shared keymap, headless dummy-driver CI. 13A exploration GUI, 13B full parity, 13C tileset + mouse. | Accepted (`0011`, 2026-07-18). 13A done — exploration GUI (`frontends/gui/`: pure `compose` + pygame `paint`/pump), shared keymap (`frontends/keymap.py`), `--frontend gui`, scene goldens, bare CI job, dummy-driver e2e. 13B done — full parity: battle/dialogue/lock views, `;` command and `:` meta bars (harness-gated), projection consistency over every view type. 13C done — click targets minted from the grammar into the Scene (`ClickTarget`, pure-geometry dispatch), pack-optional `tileset.toml` glyph→image tables as a paint-time skin (`--tiles`; reference pack ships one, regenerated via `tests/regenerate_tiles.py`). **Scope note:** `0011` proved the pipeline, not usability — its "usability claim" and pixel-hash open question are retired/absorbed by `0012` |
| 14 | **Graphical presentation** (`0012`): tiered frames, a `compose(frame, manifest) → SceneGraph` seam, deterministic click-to-move, and a UE5-MCP presentation host (isolated), with the pygame GUI as headless fallback. 14A tiered frame, 14B SceneGraph + click-to-move, 14C UE5 importer/preview, 14D substrate ratification. | Draft (`0012`, 2026-07-18). 14A done (#14) — `GridView` carries ground/fixture/actor cells with `flatten()` projecting the declared precedence; plain/TUI project identically to before, the GUI scene composes layered cells (ground persists under actors), frame wire bumped to `glyphwright.frame/6`. The real-CC0-pack tileset swap is deferred: the Kenney roguelike sheet proved near-entirely architectural, so correct character/item tiles could not be selected verifiably without a human art pass — placeholder set retained for now. 14B done (#15) — a pygame-free `frontends/presentation` package: the pure seeded A* `find_path`, the click-to-move macro that expands a click to kernel-validated `Move` tokens (with a recording replay proof that a click session is byte-identical to typing the moves), the validated `presentation.toml` manifest whose hash rides the composed graph, and `compose(frame, manifest) → SceneGraph` with tier-ordered placements, a deterministic camera, move-transition descriptors, and grammar affordances. Goldens (`sg_village`, `sg_battle`) and a projection-consistency test (topmost placement == `flatten` glyph at every cell, asserted on both the omniscient village and the FOV-fogged warren) back the 0012 §2 bridge. Review hardening: manifest decoration/hints are JSON-validated at load (a TOML `datetime` is a located `ManifestError`, not a late `compose` crash), the pack's own manifest is load-tested, and click-on-own-cell (`()` vs `None`) and click-through-fog are pinned as conscious contract. 14C done — an isolated `frontends/presentation/ue5` package behind its own `ue5 = ["mcp"]` extra (mirroring the GUI's isolation, with the bare-suite import-clean proof): an async MCP client over streamable-HTTP wrapping the editor's `list_toolsets`/`describe_toolset`/`call_tool` meta-tools with an injectable transport (verified offline against fakes and live against a running editor), a pure deterministic `plan_spawns` mapping a `SceneGraph` to a `SpawnOp` list (grid→cm projection via the manifest's `tile_size_cm`/`tier_height` hints, stable collision-free actor names, canonical sort so equal graphs plan identically) with `apply` executing a plan through the client, and an opt-in `ue5` pytest mark whose e2e (level query, semantic-anchor list carrying `worldStateKey`, spawn+remove, posed `CaptureViewport`→PNG) is verified green against a live editor but skips in the standard suite and bare job. Live findings folded into the client: `add_to_scene_from_class` returns the actor `refPath` (the handle `remove_from_scene` needs) and `CaptureViewport` requires `annotations={}`. The §5/§6 manifest/oracle session-fingerprint term is a versioned-protocol change; 14C deferred it to 14D, and 14D moved it to 15A (recorded in 0012 §10). A live viewport capture probe (`tests/goldens/ue5_capture_probe.png`) is committed as human-facing pixel evidence. 14D done — **substrate C ratified** as the human-facing path (0012 §7 Ratification): 14C's tested seam (isolated client + deterministic importer + opt-in live e2e) is the confirming evidence, so UE5 stays the presentation host with pygame as the guaranteed headless fallback and B dormant. Ratification is documentation-only and deliberately honest about its limits: the §6 two-tier oracle model is adopted in principle but **not yet exercised** (no code consults UE5 for navigation/collision), and the deferred `glyphwright.session/2` fingerprint change is **moved to 15A** because the anchor-fidelity (§11.1) and oracle-identity/correction-replay (§11.5) questions that gate a *stable* oracle fingerprint were not resolved by 14C — writing the protocol field before that evidence would encode a guessed contract. §11 open questions re-scoped accordingly: 11.1/11.5 gate 15A's protocol change (both **resolved** in 15A — see row 15); 11.2 gates only whether 15A's oracle evidence is reproducible in CI; 11.3/11.4 stay dormant |
| 15 | **Oracle model + session fingerprint** (`0012` §6/§10, 15A): resolve the live-editor questions gating the two-tier oracle model — anchor fidelity (can a UE5 anchor carry a GlyphWright semantic position as a first-class identity?) and oracle identity + correction replay (what is a stable oracle fingerprint; how does a Tier-2 collision-corrected run reproduce deterministically?) — then bump the session schema to `glyphwright.session/2` carrying the optional manifest + oracle fingerprints, with written rationale and replay-compatibility review. The slice where UE5 first becomes a navigation/collision **oracle**, not just a presentation host. | In progress. 15A contract **pinned** (#19, 2026-07-19): §11.1 anchor fidelity resolved (anchors carry semantic positions via the engine-authoritative `WorldState/<Map>.json` — locations keyed by semantic id + `bindings` key→guid; no MCP write tool), and §11.5 resolved as a design decision — the oracle fingerprint is **coarse** (level path + plugin version + semantic-position set, one opaque hashed string), collision drift is caught by a **separate on-demand drift-detection audit** (re-`trace_world` the passable-edge set; the fine per-run trace-hash was rejected as O(grid) and over-invalidating), and a Tier-2 collision correction is **captured in the recorded commands upstream of the kernel** — the click-to-move macro reroutes and emits the corrected `Move` sequence, which the kernel processes like any moves, so replay reproduces the corrected path by re-executing the recorded commands; no oracle seam in the kernel, no correction *event* folded into state (which replay could not reproduce), per-step reroute annotation being optional recording metadata outside the event digest. Drift detector verified live (`trace_world`: through-wall → hit distance, beside → null; only collision-mesh geometry registers). `glyphwright.session/2` **implemented** — the header carries optional `oracle` (`{level, plugin, positions}`) + `manifest` terms (absent for Tier-1), the schema golden is bumped to `session.v2`, and replay is **backward-compatible**: it accepts both `session/1` and `session/2` headers (a `session/1` header reads as `session/2` with both terms absent), so every pre-existing Tier-1 recording still verifies; oracle/manifest are opaque to replay, which re-executes the recorded commands and never re-consults the oracle. Replay-compat tests cover legacy-`session/1` replay, unknown-schema refusal, and oracle/manifest carriage. Remaining: the drift-detection audit tool (on-demand; needs editor) and wiring a live Tier-2 run to actually populate the oracle fingerprint |

## Next integration step

`0010-termverify-integration-assessment.md` (2026-07-18) surveys TermVerify's state and
records the asks filed as `hoelzl/termverify#114`. The direct in-process adapter spike is
**done** (`spikes/termverify-direct-adapter/`, `0010` §6): validated deterministic
`termverify.transcript/v1` from a scripted session, one API gap found and fixed (wire
codec now on `glyphwright.api`). The JSONL subprocess and PTY flavors, and all
differential testing, remain blocked on TermVerify-side work; adapter placement
(`0003` §20.5) stays open until a real conformance suite exists.

## Open questions

`0003` §20 holds the live list: adapter placement (§20.5) is the only question still open. Repository placement (own repository) and the TUI substrate (hand-rolled ANSI) were resolved on 2026-07-17; the snapshot format (replay as the durable format, slice 11) and FOV/visibility (pack-level option, slice 9A) on 2026-07-18.
