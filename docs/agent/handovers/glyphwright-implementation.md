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
| 3 — Battle | **Done** (3A exploration combat + 3B menu battle: mode stack, rolled initiative, MenuView, flee, victory/defeat outcomes; tactics arena deferred to a later slice with FOV) |
| 4 — Rooms and portals | **Done** (RoomGraphSpace, Portal component as extra exit tokens, RoomView + plain prose round-trip, inn interior in the reference pack; frame schema v3; PR pending review) |
| 5 — TUI | **Done** (hand-rolled ANSI, §20.1 resolved in 0003; pure `paint`, grammar-gated hotkeys, `;`/`:` bars, alt-screen loop, reviewed goldens; PR pending review) |
| 6 — Dialogue and one minigame | **Done** (dialogue trees + lockpicking as ordinary modes, `FocusSet` cursor, event v5 + frame v4; PR pending review) |

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

## Slice 3B decisions (menu battle)

1. **Engagement is a scheduler behavior**: `AiBehavior.engages` hostiles push a battle
   (`ModePushed(mode="battle", initiative=…)`) on contact instead of trading skirmish
   blows; the initiative order is rolled d20 + spd at push. The reference pack's
   `bandit-1` engages; `goblin-1` stays a skirmisher — both scheduler configurations
   of ADR-004 stay exercised.
2. **Battle grammar**: `attack`/`use`/`flee`/`look`; `skill` waits for the abilities
   system (§9.2). Menu battle abstracts distance; combatants are simply in the fight.
3. **Flee gains ground**: pops the battle (`outcome="fled"`) and moves the player
   through the passable exit maximizing the distance to the nearest foe; when
   cornered, `FleeFailed` spends the turn and the battle continues. A fled foe stays
   aggroed, chases, and re-engages on contact.
4. **Outcomes are checked in `step` after AI turns**: no living foes on the initiative
   list → `ModePopped(outcome="victory")`; `player-defeated` → `outcome="defeat"`.
   The `ActorDied` fold prunes the initiative queue.
5. **Nearby fighting hostiles join the battle** (post-review): engagement enrolls the
   engager plus every hostile in the area that is aggroed or in melee range, so
   nobody freezes mid-fight and battle cannot be used as a shield. Hostiles that are
   neither aggroed nor adjacent stay out (and stay suspended while battle is on top;
   revisit if off-battle simulation is ever wanted).
6. **Wire**: frame schema v1 → v2 (`viewport` is now `oneOf` grid/menu), event schema
   v3 → v4 (`ModePushed`/`ModePopped`/`FleeFailed`); same retire-and-replace policy.
   The plain transcript renders combatants as `* <id> <hp>/<max>` lines, and
   `PlainProjection` gained a `combatants` field.
7. **Initiative is behaviorally real** (post-review): foes that outroll the player
   strike pre-emptively in the engagement round; in later rounds the player's command
   resolves first by the command-driven convention and initiative orders the foes.
8. **Flee must actually escape** (post-review): scored against every hostile in the
   area, and it succeeds only if the destination breaks melee contact with the
   battle's foes — otherwise `FleeFailed`. A fled foe still chases and re-engages on
   its own later turns.
9. **Honest rejections across modes** (post-review): each mode declares its verb set
   (`Mode.VERBS`); a mode-absent verb rejects as `wrong_mode` with the mode's actual
   options, never "there are no exits here".
10. **Glyph vocabulary is content** (post-review): `Renderable` carries a `label`,
    legends are built from the pack per area, and the plain parser identifies tile
    rows structurally (leading space-free lines) instead of via a hardcoded charset.
    Plain help is derived from the frame's grammar, so it cannot drift.
11. **Initiative survives nested pushes** (post-review): a push without an initiative
    payload preserves the queue; only popping the battle clears it. Battle outcomes
    are checked in the scheduler's battle configuration (one shared loop, ADR-004) —
    §10.1's "checked in the event fold" is read as "checked during the fold inside
    step", since a fold that emits events is not implementable in this design.

## Slice 4 decisions (rooms and portals)

1. **Portals are entities** (`Portal(token, to)`, 0003 §7.4): a portal standing at a
   position contributes one extra exit token there; twins are authored explicitly,
   like room exits (one-way in data, mirroring the Riches convention). `move
   <exit-token>` remains the only movement command; the *destination's* space
   answers passability, so a portal may land in a different area.
2. **Rooms never block on occupancy**: bodies do not fill a room. `blocked_reason`
   is reserved for `closed`/locked exits when flag-gated doors arrive (the
   rusty-key exists for that day).
3. **RoomView** carries room id, name, description, contents (items and actors,
   not portals), and the merged exit list. The plain transcript renders prose with
   an `Exits: …` anchor line; `PlainProjection` gained `room` and `exits` fields.
4. **One movement graph for everyone** (post-review): `WorldState.exits_from` (space
   exits + portals) feeds the player's grammar *and* AI pursuit — a door the player
   can use is a door a pursuer follows through. Chase/escape BFS runs over that
   cross-area graph, so foes in other areas neither freeze pursuit nor crash flee.
5. **Pack identity hashes areas via `asdict`** (with `kind` and a public `area` key);
   the pin was deliberately re-pinned.
6. **Melee is answered by the geometry** (post-review): `Space.melee_range` — grid
   says one exit away, room graph says the same room (a neighbouring room is behind
   a wall). Same-room combat works; through-the-wall combat cannot happen.
7. **Content is validated at construction** (post-review): `ContentPack` rejects
   portals that stand nowhere/off-map, lead nowhere, shadow a geometric exit, or
   collide on a token; `RoomGraphSpace` rejects duplicate exit tokens and
   transcript-unsafe prose (newlines, lines imitating `Exits: `/`* `/`== ` markup).
   `_move` still guards unknown areas defensively with a `MoveBlocked("edge")`.
8. **Every room block closes with an `Exits:` anchor**, `Exits: none.` for dead
   ends, so the plain parse round-trip holds for any authored room.

## Slice 5 decisions (TUI)

1. **Hand-rolled ANSI over Textual** — resolution recorded in 0003 §20.1 itself,
   following the §20.4 precedent. Turn-based → blocking key/step/repaint loop, no
   async runtime, zero dependencies, byte-deterministic screens.
2. **`paint(frame, log)` is pure**: fixed line budgets per region (header, viewport,
   status, log, hint bar), full repaint per turn, clear-and-home as the only cursor
   ANSI. `\r\n` line endings for raw-terminal correctness.
3. **Hotkeys are grammar-gated**: a key whose verb is not advertised does nothing;
   `t/u/e/a` take the first advertised referent; digits pick move-domain entries in
   listed order; `;` opens a typed command bar (full language), `:` the meta bar
   (harness-gated). The keyboard can never say what the grammar cannot.
4. **Reviewed goldens** live in `tests/goldens/` (TUI screens + plain blocks) with
   `tests/regenerate_goldens.py`; regeneration is deliberate and the PR diff is the
   human review.
5. **Real-keyboard input** (`keys.read_keys`) is the only untested code path
   (platform raw-console reads, `pragma: no cover`); scripted iterators drive the
   loop everywhere else. TermVerify-side PTY differential tests remain external
   (§20.5).

## Slice 6 decisions (dialogue and lockpicking)

1. **Mode-local cursors are one state field**: `WorldState.focus = (entity, detail)`,
   installed by the `FocusSet` event — dialogue tracks `(speaker, node)`, lockpicking
   `(chest, pins-set)`. `DialogueLine`/`ChoiceOffered`/`PinSet`/`PinSlipped` are pure
   evidence; `ModePopped` clears focus. If two focus-modes ever nest, focus needs
   per-frame stacking like initiative — revisit then.
2. **Dialogue trees are components** (`Dialogue`/`DialogueNode`/`DialogueChoice` on the
   speaker entity), validated at construction (unique ids, resolvable links, every
   node offers a choice). Choice effects: `sets_flag` only; item grants and mode
   pushes from choices are future work.
3. **`Openable(contains, key)` + the shared `unlock_events`**: the rusty key opens the
   strongbox outright; without it, `open` pushes `minigame:lockpick`. One unlock path
   serves both, so a chest cannot behave differently by how it was defeated.
4. **Lockpicking is roll-per-attempt** (d20 >= 9 sets the next of 3 pins; a slip
   resets) — no secret stored in state, so nothing special is needed for replay.
   `abort` pops with outcome `abandoned` and the chest stays available.
5. **Wire**: event v4 → v5, frame v3 → v4 (dialogue + lock viewports); same
   retire-and-replace policy. Plain marks dialogue lines with `| ` and the lock line
   with `% ` (parse cuts the room block first, so prose is safe from the markers,
   and room prose bans them at construction); TUI digits choose when a dialogue is
   open, `p` picks, `z` aborts.
6. **The world does not stop for talk or locks** (post-review): dialogue and
   lockpick serve the same activity list as exploration, so an aggroed hostile
   chases mid-conversation and an engager interrupts with a battle pushed on top;
   `ModePopped` clears focus only for focus-owning modes, so the conversation
   resumes after the fight. Defeat mid-focus-mode collapses the stack to the
   defeated grammar.
7. **Load-time guarantees** (post-review): dialogue trees must have a reachable
   farewell; `Openable.contains`/`key` must reference pack entities. The key path
   leaves `ItemUsed` evidence; openables are listed in room contents.

## Slice 7 decisions (abilities, statuses, primitives — design 0004)

1. **Design doc 0004** scopes 0003 §9.2–§9.3; it is subordinate to 0003. Read it
   before touching `effects/primitives.py` or `effects/abilities.py`.
2. Three primitives ship (`deal_damage`, `heal`, `apply_status`); `deal_damage`
   shares `resolve_damage` with `strike`, so ability kills and weapon kills are the
   same kind of fact. Ability/status tables ride in `WorldState`
   (`ability_defs`/`status_defs`) so handlers resolve them from kernel inputs.
3. **`cast <ability> at <target>` is the first arity-two verb**; the per-position
   domain encoding (0003 A.2) holds, and the ability×target cross-constraint is a
   world refusal (`CastFizzled`, turn spent) per 0003 A.5 — never a rejection.
4. **Statuses are timed modifier bundles**: `Statuses` component `(id, expires)`,
   `StatusApplied`/`StatusExpired` folds, expiry swept in the scheduler epilogue,
   pipeline provenance `"<id> (status)"` (statuses before equipment). Hooks and
   perks (0003 §9.3) deferred — recorded in 0004.
5. **No resource costs yet**: `requires_stat` is the only gate; inventing a
   throwaway mana pool was deliberately declined (0004 §2).
6. Event schema v5 → v6 (`StatusApplied`/`StatusExpired`/`CastFizzled`).

## Slice 8 decisions (TOML content packs — design 0005)

1. Four-file layout (`pack.toml`, `areas.toml`, `entities.toml`, `abilities.toml`);
   positions are `"area:local"` strings; components mirror the dataclasses.
2. The loader adds *location*, not a second validation layer: constructor errors are
   re-raised as `PackError` with file + table + id; tomllib syntax errors carry
   line/column. `0003` §8.2's "file/line" reads as: lines for syntax, exact content
   object for semantics (recorded in 0005 §3).
3. **The reference pack is TOML now** — `reference_pack()` loads the packaged files
   (`importlib.resources`), so the entire suite exercises the loader; the
   Python-built pack was deleted, not shadowed. The wheel verifiably ships the
   files.
4. `--pack <dir>` on the CLI, failing with a clean argparse error on broken packs.
5. `tomllib` is stdlib: the zero-dependency stance holds.

## Slice 9A decisions (field of view — design 0006 §1)

1. **FOV is a pure view filter**: `GridSpace.fov` radius (pack option, `fov = N`
   on grid areas; rooms reject it), Chebyshev range + Bresenham line-of-sight,
   walls visible but opaque. No state, no events, no explored-tile memory — the
   fold, replay, and grammars are untouched by construction (tested).
2. Unseen tiles render `?` (parse-safe under the space-free tile rule; legend
   `? = unseen`); unseen entities are neither drawn nor summarised, and
   `observe()` filters the same way. The oracle stays an x-ray. AI keeps its
   ears (pursuit of an unseen player is deliberate).
3. The reference pack stays omniscient (golden stability); the tactics arena
   (9B, sketched in 0006 §2) will ship fov-enabled content.
4. The `fov` field widened grid-area identity; the pack pin was re-pinned.

## Slice 9A post-review decisions

1. **Frames disclose the here and now**: exploration `ActorSummary` rows list only
   the player's current area (FOV or not), and in a fov-active area only visible
   actors; messages are filtered the same way (an unseen actor's movement is not
   narrated). The oracle stays the x-ray.
2. **Sight is symmetric by construction**: Bresenham in either direction counts.
   `visible_from` raises on foreign/off-map origins. `fov = 0` is accepted as
   explicit omniscience; `?` is a reserved glyph (loader-enforced).

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
