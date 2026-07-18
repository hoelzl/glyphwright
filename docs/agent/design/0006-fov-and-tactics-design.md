# Field of View and the Tactics Arena — Design Document

| | |
|---|---|
| **Status** | Accepted — subordinate to `0003`; §2 (tactics) is a forward sketch |
| **Date** | 2026-07-18 |
| **Scope** | Scopes `0003` §20.3 (FOV) and §10.1's tactics battle into slices 9A/9B |
| **Authority** | `0003` wins on any disagreement; this document only refines it |

## 1. Field of view (slice 9A)

`0003` §20.3 deferred FOV until tactics battles want it. They are next, so it
lands now — as the smallest thing that satisfies §20.3's phrasing: a
**pack-level option**, and a **pure view filter**.

- **Content**: a grid area may declare `fov = <radius>` (`areas.toml`; absent
  or an explicit `0` means omniscient, today's behavior — every existing pack
  and golden is untouched). Negative radii are load errors; room areas reject
  the key (a room *is* its own horizon). The glyph `?` is reserved for unseen
  tiles: a renderable claiming it is a load error.
- **Visibility rule**: a tile is visible when its Chebyshev distance is
  within the radius **and** a Bresenham line in *either* direction connects
  observer and tile without crossing an interior wall; walls themselves are
  visible (you can see a wall, not through it). The either-direction rule
  makes sight symmetric by construction — two actors always agree on mutual
  visibility. Deterministic, integer-only; no diagonal-corner subtleties are
  promised beyond symmetry.
- **No state, no events**: visibility is a function of the observer's
  position and the terrain. There is no explored-tiles memory — that would
  be state, events, and schema; if fog-of-memory is ever wanted it is its
  own decision. This is what keeps FOV a *view* concern (`0003` §11):
  `step`, the fold, and replay are untouched by construction.
- **Presentation**: unseen tiles render as `?` (ASCII, parse-safe under the
  plain frontend's space-free tile rule; legend entry `? = unseen`).
  Entities on unseen tiles are not drawn; `ActorSummary` rows list only the
  player's *current area*, and in a fov-active area only visible actors —
  a harness reads the same truth the player sees, and no frame leaks intel
  about other areas. Messages are filtered the same way: an unseen actor's
  movement is not narrated. `observe()`'s `visible`/`actors` filter
  identically, honouring the `SpatialObservation` contract at last; a
  foreign or off-map origin raises rather than reporting blindness.
- **What does not change**: grammars (attack needs adjacency, which is
  always visible; items are underfoot), AI (hostiles have ears — pursuing
  an unseen player is fine and keeps the scheduler untouched), and the
  oracle (`:query` is the harness's x-ray, not the player's eyes).

## 2. The tactics arena (slice 9B)

`0003` §10.1: the battle mode instantiates a `GridSpace` arena; movement and
range reuse the spatial model unchanged. Detailed for implementation:

- **Content**: `AiBehavior` gains `arena = "<area>"` — an engaging hostile
  that names an arena opens its battles *there* (a plain engager without one
  keeps the menu presentation; both stay ordinary battles on the same mode
  and scheduler). Pack validation: the arena must name a grid area and hold
  enough floor for the combatants; portals inside an arena are rejected
  (a battlefield has no back doors — `flee` is the exit).
- **Entering**: engagement emits ordinary `Moved` events after the
  `ModePushed`: the player to the first free floor tile in row-major order,
  then the foes in initiative order to the next free tiles. `ModePushed`
  carries a `returns` table (`(combatant, origin)` pairs) that the fold
  installs as `WorldState.battle_returns` — the way home is state, so it
  replays (event schema v6 → v7).
- **Fighting**: with `battle_returns` set, the battle frame's viewport is
  the arena's `GridView` (frame schema already admits it — no bump) and the
  verbs are `move`/`attack`/`cast`/`flee`/`look`. `attack` needs melee
  adjacency on the grid; `cast` foe-targeting reaches any living foe (magic
  outranges steel — the first ranged/melee distinction, deliberately given
  to abilities). Foes chase-or-strike using the same pursuit logic as
  exploration; the arena's own `fov` applies to the viewport like any grid.
- **Leaving**: every battle pop (victory, defeat, flee) is preceded by
  `Moved` events returning each *surviving* combatant to its recorded
  origin; the `ModePopped` fold clears `battle_returns`. Arena `flee` obeys
  the same break-contact rule as menu flee: after the homecoming the player
  takes one escaping step (scored against every hostile), and if no step
  breaks melee contact with the battle's foes the flee fails — returning to
  a tile beside an aggroed engager cannot count as escaping.
- Everything is events; nothing new enters the kernel beyond the
  `battle_returns` field and its two fold arms.

## 3. Non-goals (9A)

Explored-tile memory, light sources, per-actor sight radii, diagonal-corner
FOV refinements, and AI vision (hostiles keep their ears). Each would be
content or state design, not a view filter.
