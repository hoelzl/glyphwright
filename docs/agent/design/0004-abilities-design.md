# Abilities, Statuses, and Effect Primitives — Design Document

| | |
|---|---|
| **Status** | Accepted — subordinate to `0003` |
| **Date** | 2026-07-17 |
| **Scope** | Scopes `0003` §9.2–§9.3 into an implementable slice (slice 7) |
| **Authority** | `0003` wins on any disagreement; this document only refines it |

`0003` §9 settles the architecture: abilities are data composing Python-implemented
effect primitives; statuses are timed modifier bundles; everything executes inside
`step` and appears in the event log. This document makes the slice-sized decisions
`0003` §18 never had to make, because its plan ended at slice 6.

## 1. Effect primitives (`effects/primitives.py`)

A registry `name -> primitive`, where a primitive is:

```python
def primitive(
    state: WorldState, source: EntityId, target: EntityId,
    params: Mapping[str, object],  # per-primitive specs: ints, plus str ids
    rng: Rng,
) -> tuple[tuple[Event, ...], Rng]
```

Each primitive declares a parameter spec (name → type); pack validation checks
every authored param against it at load, and the key ``ability`` is reserved
for the engine's evidence labelling. Malformed params are load-time errors,
never mid-session crashes.

Slice 7 ships three, chosen because each exercises a different consequence shape:

| Primitive | Params | Events |
|---|---|---|
| `deal_damage` | `amount` (fixed), `spread` (rng 0..spread added) | `DamageDealt` (+ `ActorDied`/defeat, via the shared death resolution) |
| `heal` | `amount` | `Healed` |
| `apply_status` | `status` (content id), `duration` (turns) | `StatusApplied` |

Primitives are total over valid content: unknown names are load-time errors
(pack validation), like every other reference. `deal_damage` reuses the defence
reduction and death/defeat rules of `strike` so an ability kill and a weapon
kill are the same kind of fact.

## 2. Abilities

An ability is content data referenced by id:

```python
Ability(id, name, targeting, effects, requires_stat=None)
```

- **Targeting**: `"self"` or `"foe"`. A `foe` ability targets like `attack`
  does — the mode's current notion of a reachable enemy (melee adjacency in
  exploration, the initiative list in battle). Ranged-vs-melee distinctions
  and area targeting stay future work.
- **Effects**: an ordered tuple of `(primitive-name, params)`; executed in
  order, folding between steps, inside the mode handler.
- **Requirements**: `requires_stat=(stat, minimum)` — the only gate in slice 7.
  Costs (mana or otherwise) need a resource pool that does not exist yet; the
  design deliberately defers resources rather than inventing a throwaway one.
  An ability the actor does not qualify for is *not advertised* (item-domain
  rule, not map-topology rule — `0003` A.5 applies to the map).

Abilities live on actors: `Actor.abilities: tuple[ability-id, ...]`; the ability
definitions themselves sit in the content pack (`ContentPack.abilities`), and
pack validation checks every referenced id, primitive name, and status id
resolves.

**Command surface**: `cast <ability> at <target>` (`0003` §6 lists exactly this
shape). The grammar entry is the first genuinely two-argument verb:
`"cast": [[abilities...], [targets...]]` — the uniform per-position-domain
encoding (`0003` A.2) was built for this, and the generic validator already
zips argument against domain. `cast` is available in exploration and battle
(`skill` from `0003` §10.1 is `cast` — one verb, not two names for the same
thing; the menu sketch named the slot, not the verb).

**The cross-constraint**: per-position domains cannot express that *this*
ability pairs only with *those* targets. The target domain is therefore the
union of every castable ability's targets, and a mismatched pairing
(`cast guard at goblin-1`) is a **refusal by the world**, `0003` A.5 exactly:
enumerable, attemptable, turn-spending, answered by a `CastFizzled` event with
a reason — never a rejection, because the grammar advertised both halves. This
keeps A.2's shape uniform and gives fuzzers a reachable refusal to find.

## 3. Statuses

A status definition is content: `Status(id, name, modifiers)` — a bundle of
`StatModifier`s. An *application* is entity state: the `Statuses` component
holds `(status-id, expires-turn)` pairs, written by the `StatusApplied` fold
and cleared by the `StatusExpired` fold.

- **Stat pipeline**: active statuses contribute modifiers between base and
  equipment, with provenance `"{status-id} (status)"` (`0003` §9.1 order:
  additive from any source before multiplicative from any source; within a
  kind, statuses before equipment, both in sorted-id order).
- **Expiry**: `expires = (turn after application) + duration`, so a
  duration-1 status survives the casting step's own turn advance and covers
  the caster's next action. At the close of any turn-spending step, the
  scheduler epilogue emits `StatusExpired` for every application whose
  `expires-turn <= turn` — in the event log like everything else, so expiry
  replays. Re-application extends the clock and never truncates it.
- **Frames**: `ActorSummary.statuses` (present since slice 1, always empty
  until now) lists active status ids.
- **Hooks** (`0003` §9.3 event-triggered effects) are explicitly out of scope
  for slice 7: they belong with the fold-hook machinery and deserve their own
  slice; nothing here forecloses them.

## 4. Events

`StatusApplied(target, status, expires)` and `StatusExpired(target, status)` —
both in `0003` §5.3's representative list. Event schema bumps v5 → v6 under the
established retire-and-replace policy (no external consumer yet).

## 5. Reference pack additions

- Player learns `firebolt` (foe-targeted: `deal_damage(amount=3, spread=3)`)
  gated on `atk >= 5`, and `guard` (self-targeted: `apply_status(stoneskin, 3)`).
- Status `stoneskin`: `def +3` while active.
- The goblin gets nothing (it stays a teeth-and-claws skirmisher); the bandit
  learns nothing yet either — AI ability use is future work, recorded as such.

## 6. What this slice proves

- The primitive registry composes: one ability chains damage after status, and
  the tests assert the fold sees both in order.
- `:query player.stats.def --explain` shows a status line with provenance while
  `stoneskin` is active and loses it after expiry — the pipeline's provenance
  claim extended to its second source kind.
- The two-argument grammar shape works end-to-end (frames, wire, fuzzing,
  rejection vocabulary) — the consumer-side uniformity claim of `0003` A.2 is
  finally exercised at arity 2.
