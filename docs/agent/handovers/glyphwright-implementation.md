# Handover — GlyphWright implementation per design 0003

Active multi-session implementation state. Read `docs/agent/design/0003-glyphwright-design.md`
first; it is authoritative over this file. Update this document whenever a slice starts,
finishes, or a decision worth carrying across sessions is made. Retire entries once the
information is recorded in design docs, knowledge bundle, or code.

## Current state (2026-07-17)

| Slice (0003 §18) | Status |
| --- | --- |
| 1 — Walking skeleton | **Done** (kernel, GridSpace, move/look/wait, plain + JSONL frontends, `glyphwright.api`, committed schemas, fingerprint; 82 tests green) |
| 2 — Items and stats | **Done** (inventory + take/use/equip, stat pipeline with provenance, meta-channel `:query/:seed/:frame`, `Engine.query`, `glyphwright.query/1` schema; PR pending review) |
| 3 — Battle | **In progress**: 3A (exploration combat + shared scheduler) done; 3B (menu battle mode, initiative queue, MenuView, flee) next |
| 4 — Rooms and portals | Not started |
| 5 — TUI | Not started |
| 6 — Dialogue and one minigame | Not started |

TermVerify-side work (direct adapter, PTY golden) is deliberately not in this repository
yet; adapter placement is open (0003 §20.5) and will be decided when the adapter is built.

## Workflow contract for sessions

- Work on a feature branch; open a PR when a slice (or coherent sub-slice) is green.
- Run an adversarial review on the PR before merging; fix confirmed findings, then merge.
- Full local gate before any PR: pytest with coverage, ruff check, ruff format --check,
  mypy strict, pre-commit (both stages). Commands are in `AGENTS.md`.
- Strict TDD for behavior changes (AGENTS.md completion contract).

## Slice 2 plan and decisions

Scope (0003 §18.2): inventory, `take`/`use`/`equip`, stat pipeline with provenance,
`:query … --explain`.

Decisions taken by the implementing agent (owner delegated open choices):

1. **`use` is arity-1 in slice 2** (`use <item>`, self-targeted). The design's
   `use X on self` surface syntax arrives when battle introduces other targets;
   keeping one argument keeps the grammar→line→parse round trip uniform.
2. **Equipment model:** equipped items stay in the inventory; an `Equipment` component
   maps slot → item id. `equip` into an occupied slot replaces (event carries what was
   replaced); no separate unequip verb yet.
3. **Consumables are destroyed on use:** `ItemUsed(consumed=True)` removes the item
   entity in the fold.
4. **Event vocabulary changes bump the schema tag** (revised after adversarial review):
   the event schema is a closed enum with `additionalProperties: false`, so widening it
   is not additive for a pinned validator. Slice 2 ships `glyphwright.event/2`; v1 was
   retired rather than kept in a compatibility matrix because no external consumer
   existed before the bump. Future widenings follow the same rule (ADR-006).
5. **Meta-channel in slice 2 ships `:query <path> [--explain]`, `:seed`, `:frame --json`**;
   `:events --since`, `:save`/`:load` are deferred until a consumer needs them
   (snapshots already exist via the API).
6. **Stat pipeline lives in `effects/stats.py`**: base → additive → multiplicative →
   clamps; every modifier carries provenance (source id + kind). Equipment is the only
   modifier source in slice 2; statuses/perks arrive with battle. Unknown modifier ops
   are unrepresentable (`StatModifier` validates at construction).
7. **Item verb domains are validity filters, unlike the map's exits** (post-review):
   `use` is not advertised when it would have no effect, because accepting it would
   destroy the item for nothing. The grammar-as-topology rule (0003 A.5) applies to
   the map; item domains were always permission-shaped (only carried items appear).
   Revisit if a consumable with a non-heal effect arrives.
8. **Pack-id derivation is pinned by a golden test** (post-review): hashing walks every
   component field via `asdict` (new components cannot silently escape identity), and
   `test_the_pack_identity_derivation_is_pinned` turns any change to the derivation —
   field rename, serialization shape — into a visible, deliberate diff. The derivation
   changed in slice 2 while no external fingerprints existed.
9. **The oracle never fabricates**: `stats` queries error (`no_such_stat`) for stats the
   entity does not declare (base stats ∪ equipped modifier stats) and for non-actors,
   while kernel-level `derive` stays total (missing stat = 0) for future battle math.

## Slice 3A decisions (exploration combat)

1. **Exploration combat is real** (0003 appendix B shows attack resolving in mode
   `exploration`): the shared scheduler (`kernel/scheduler.py`) grants AI turns inside
   `step` after any turn-spending command. Battle mode (3B) will configure the same
   scheduler with an initiative queue (ADR-004).
2. **Melee is adjacency**: `attack` domains list adjacent hostiles only. A.2's sketch
   showing a distant goblin as attackable is read as sketch looseness; ranged attacks
   arrive with abilities (§9.2).
3. **`attack <target>` is arity-1** like `use`: the weapon is the equipped one, until
   abilities introduce explicit weapon choice (`attack X with Y`).
4. **Hostiles are passive until provoked** (attacked, or player steps adjacent);
   aggression is a world flag (`aggro:<id>`) set by a `FlagSet` event so it replays.
   Aggroed hostiles chase via BFS over the `Space` protocol (geometry-independent).
5. **The player never dies through `ActorDied`**: defeat is the `player-defeated` world
   flag; the grammar collapses to `look`. Interim until 3B gives defeat a real outcome
   via `ModePopped`.
6. **Combat math** (`effects/combat.py`): to-hit `d20 + atk >= 10 + def`; damage
   `1..atk` minus `def // 2`, min 1; one `strike` function serves player and AI.
7. **Event schema bumped v2 → v3** (DamageDealt, AttackMissed, ActorDied, FlagSet);
   same retire-and-replace policy as v1 → v2 while no consumer exists.
8. **The closing `TurnAdvanced` carries the round's RNG cursor** (post-review): RNG
   draws are state changes, so they must be evidenced or the fold cannot reproduce the
   successor (§5.3). `step` stamps the cursor into the round's final `TurnAdvanced`
   (wire field `rng`, opaque token); the fold applies it; `fold(prior, events) ==
   successor` now holds *exactly*, cursor included, and is tested as full equality.
   Corollary rule, enforced in `step`: a handler must not draw without spending the
   turn.
9. **Provocation and death bookkeeping** (post-review): only survivors are provoked
   (a corpse does not snarl), and the `ActorDied` fold clears the actor's aggro flag.
   Flag vocabulary (`aggro:<id>`, `player-defeated`) lives in `kernel/events.py`
   beside `FlagSet`. Post-defeat rejections use reason `defeated` instead of
   misdescribing the world.

## Next steps

1. Finish slice 2 (see task breakdown in session, or re-derive from §18.2).
2. Slice 3 — battle: menu battle first, shared scheduler (§5.5, ADR-004), then tactics
   arena reusing GridSpace. Statuses/perks hook into the event fold (§9.3).
3. Slice 4 — rooms and portals: `RoomGraphSpace`, mixed-world reference pack.
   `C:\Users\tc\Programming\TypeScript\Projects\Riches` may be browsed for room-mode
   inspiration/assets (owner note: not authoritative, no 1-1 replication).

### Riches survey notes (2026-07-17, for slice 4)

Surveyed `Riches` (TypeScript, YAML-authored room games). Distilled ideas worth adapting —
adapt to 0003's `Space`/portal/event model, do not copy the architecture:

- Rooms: id/slug + display name + prose description + exits map + contents + tags.
  Exits authored per-room and one-way in data (reverse links authored explicitly);
  built in two passes (rooms, then exit wiring) so destinations resolve.
- Exit shape: shorthand (`north: room-id`) or expanded (`{destination, active, description}`).
  `active: false` = state-blocked exit → in GlyphWright terms `blocked_reason "closed"`,
  toggled by effect primitives and gated by flags. Clean lock/key primitive.
- Conditional room descriptions: base prose + `{condition, append}` modifiers — fits
  GlyphWright as flag-gated description fragments rendered in `RoomView`.
- Item `discovered`/`visible` flags and `on_player_enter`/`on_item_taken`/`one_shot`
  hooks — GlyphWright equivalents belong in status/hook machinery (§9.3), not ad-hoc.
- Scale template: 8–9 rooms per hand-authored world. Two themes there: "Classic Dungeon"
  (light-vs-shadow fantasy crawl: Vestibule, Enchanted Study, Library of Echoes, Silent
  Chamber, Treasure Chamber…) and a theater murder mystery. For the reference pack's
  room area, an 8-room interior (e.g. an inn or study wing) portal-linked to the village
  grid would satisfy §7.4's acid test at similar scale.
4. Slice 5 — TUI (decide Textual vs hand-rolled with a spike, §20.1).
5. Slice 6 — dialogue + one minigame.
