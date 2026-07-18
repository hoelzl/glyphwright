# Resource Pools and Ability Costs — Design Document

| | |
|---|---|
| **Status** | Accepted — subordinate to `0003` and `0004` |
| **Date** | 2026-07-18 |
| **Scope** | Lifts `0004` §2's deliberate deferral of costs into slice 12 |
| **Authority** | `0003` wins on any disagreement; this document only refines it |

`0004` §2 deferred ability costs because "a resource pool does not exist yet"
and refused to invent a throwaway. This document builds the pool the honest
way: one resource, shaped exactly like hp, flowing through the same events,
frames, and oracle as everything else.

## 1. The pool

`Actor.mp` / `Actor.max_mp`, both defaulting to 0 — every existing actor and
pack is untouched, and `max_mp = 0` *means* "no pool" everywhere downstream
(frames omit it, items that restore it are not offered). One pool, named
plainly; a second resource kind would be a content-design decision with its
own document, and nothing here forecloses it.

## 2. Costs

- `Ability.cost: int = 0` — mp. **Affordability is advertisement** (the
  item-domain rule, exactly like `requires_stat`): an unaffordable ability
  is not offered by `castable`, for the player and the AI alike — a caster
  that runs dry stops being advertised a cast and, in `_pursue`, falls back
  to the chase branch. Running out of mana turns a turret back into a
  pursuer with zero new AI machinery.
- Casting emits `ManaSpent(caster, amount)` *before* the effect chain; the
  fold decrements. A fizzled cast spends no mana — the cast never resolved,
  and the turn is the fizzle's price (`0004` §2's refusal semantics are
  unchanged).

## 3. Recovery

`Consumable.mana: int = 0` — the potion shape, extended: a consumable may
restore hp, mp, or both. `usable_items` offers it when it would do
something (`heal` against a wound, `mana` against a spent pool); use emits
`Healed` and/or `ManaRestored(target, amount, source)` with post-clamp
amounts (events are evidence of what happened, not what was attempted).
No passive regeneration: a regen status is already expressible as a
`turn_end` hook when content wants one (design `0007`), so the engine adds
nothing.

## 4. Surface

- **Frames**: `ActorSummary.mp: (current, max) | None` — `None` when the
  actor has no pool. Frame schema v4 → v5; the plain status line becomes
  `[hp 17/20 mp 4/6]` when a pool exists (parse updated, goldens
  regenerated deliberately). Event schema v8 → v9 (`ManaSpent`,
  `ManaRestored`).
- **Oracle**: `<entity>.mp` answers `[current, max]`, exactly like `hp`.
- **Validation**: negative `cost`, `mana`, or `mp`, and `mp > max_mp`, are
  load errors.
- **Reference pack**: the player gets mp 8/8, firebolt costs 2, guard 1,
  rockshard 2; the hexer gets mp 6 — three casts, then it must close in.
  A `tonic` (restores 4 mp) joins the village floor.

## 5. Non-goals

Multiple resource kinds, passive regeneration in the engine, costs on
non-cast actions, and resource-draining attacks. Each is content design
for another day; the pool, the events, and the frames they would need all
exist after this slice.
