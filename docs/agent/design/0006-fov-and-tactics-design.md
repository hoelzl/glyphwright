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

## 2. The tactics arena (slice 9B, sketch)

`0003` §10.1: the battle mode instantiates a `GridSpace` arena; movement and
range reuse the spatial model unchanged. The intended shape, recorded now and
detailed when 9B starts:

- A pack declares an `arena` grid area (fov optional). An engaging hostile
  with `tactics = true` opens a battle *in the arena*: combatants' positions
  are moved there by ordinary `Moved` events (deterministic placement:
  player at the first floor tile, foes in sorted-id order after), and the
  battle mode's verbs become `move`/`attack`/`cast`/`flee` over the grid.
- Victory/defeat/flee move the survivors back the same way. Everything is
  events; nothing new enters the kernel.

## 3. Non-goals (9A)

Explored-tile memory, light sources, per-actor sight radii, diagonal-corner
FOV refinements, and AI vision (hostiles keep their ears). Each would be
content or state design, not a view filter.
