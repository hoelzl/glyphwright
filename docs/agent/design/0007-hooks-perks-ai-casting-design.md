# Status Hooks, Perks, and AI Ability Use — Design Document

| | |
|---|---|
| **Status** | Accepted — subordinate to `0003` and `0004` |
| **Date** | 2026-07-18 |
| **Scope** | Scopes `0003` §9.3 (hooks, perks) and `0004` §5's deferred AI ability use into slice 10 |
| **Authority** | `0003` wins on any disagreement; this document only refines it |

`0004` shipped abilities, statuses-as-modifier-bundles, and effect primitives,
and explicitly deferred three things: event-triggered status hooks, perks, and
hostiles that cast. This document lands all three on the machinery `0004`
built — no new primitive kinds, no new command surface.

## 1. Status hooks

A status definition gains `hooks`: event-triggered effect chains
(`0003` §9.3: "on `DamageTaken`, if HP < 25%, apply `last-stand`").

```python
Hook(on, effects, hp_below=None)
```

- **Triggers** (`on`): `"damage_taken"` — a `DamageDealt` event whose target
  is the holder — and `"turn_end"` — the round's closing `TurnAdvanced`
  (which exists exactly once per turn-spending step). Two triggers exercise
  the two shapes that matter: reacting to what happened to you, and acting
  on the clock (`turn_end` + `deal_damage` is poison; `turn_end` + `heal`
  is regeneration). The vocabulary is closed and validated at load.
- **Condition**: `hp_below = <percent>` (integer 1–99, optional) — fires only
  while `hp * 100 < max_hp * percent`, evaluated against the state *as of the
  triggering event*: the pass replays the round's events forward from the
  step's opening state, so a status applied later in the round never fires
  retroactively and the gate reads the hp the holder actually had at that
  moment. The one condition `0003`'s example needs; a richer predicate
  language is content design for another day.
- **Effects**: the same ordered `(primitive, params)` chains abilities use,
  validated identically at load. Hook effects are **self-directed**: source
  and target are the holder. (Attacker-directed effects — thorns — need
  event-context targeting and are deferred; recorded here so the deferral is
  a decision, not an oversight.)
- **Execution**: hooks fire inside `step`, in the scheduler epilogue, after
  the AI round and before the status-expiry sweep. The pass scans the whole
  round's events (player's and AI's alike) in order; for `damage_taken` the
  holder is the event's target, for `turn_end` holders iterate in sorted-id
  order, and each holder's bearings fire statuses before perks, sorted by id.
  Consequent events are ordinary primitive events, appended to the log and
  folded — so hook effects replay exactly, and a poison tick that kills the
  last foe ends the battle in the same step, through the ordinary outcome
  check.
- **One generation per step**: events produced by hooks do not trigger
  further hooks within the same step. This closes the recursion question by
  construction (no cascade caps, no cycle detection) at the cost of
  hook-on-hook combos, which nothing in `0003` requires. A dead holder's
  remaining hooks are skipped; evidence labelling reuses the reserved
  `ability` param, set to the status id.

## 2. Perks

`0003` §9.3: a perk **is** a permanent status acquired through progression.
Therefore perks reference the same status definitions:

- `Actor.perks: tuple[status-id, ...]` — authored on actors like
  `abilities`; no expiry clock, no `Statuses` entry.
- The stat pipeline adds `_perk_modifiers` with provenance
  `"{id} (perk)"`. Order within a kind: perks, then statuses, then
  equipment (permanent before temporary before worn), each sorted by id;
  the global additive-before-multiplicative rule is unchanged.
- Perk hooks fire exactly like status hooks (after them, per holder).
- **Acquisition**: `PerkGained(target, perk)` — a new event whose fold
  appends to `Actor.perks` (idempotent: re-gaining an owned perk is
  evidence, not duplication). The `grant_perk` primitive
  (`params: perk`) emits it, so any effect chain — an ability today, a
  dialogue action or quest reward when those exist — can grant one.
  There is no XP system; progression *mechanisms* stay future work, the
  progression *fact* (the event) is now expressible.
- Frames do not list perks (statuses stay the `ActorSummary` surface);
  the oracle shows them through `stats --explain` provenance and entity
  queries. Event schema bumps v7 → v8 (retire-and-replace, no consumer).

## 3. AI ability use (`0004` §5's future work)

One rule, no new AI state: **a hostile casts when it cannot strike.**

- In `_pursue` (exploration hostiles and arena foes share it): if the foe
  is melee-adjacent it strikes, as today; otherwise, if the player is in
  the foe's own area and it has a castable foe-targeting ability, it casts
  the first (sorted by id, `castable`'s existing order and gates) at the
  player; otherwise it chases. The area gate matters: a caster has ears
  but not artillery — a player who leaves the area is pursued through the
  movement graph, never bombarded across it.
- Durations mean the same thing for every caster: the chain runner tells
  duration-granting primitives whether the step's turn advance is still
  pending (a player cast) or already folded (an AI cast or a hook), and
  `apply_status` compensates, so a duration-3 venom covers three of the
  holder's turns no matter who applied it.
- Menu battles abstract distance — a combatant can always strike — so menu
  foes keep striking; "magic outranges steel" is precisely the advantage
  distance-abstraction erases.
- AI casts reuse `cast_events` with the turn-advance suppressed (only the
  player's command closes a turn); the pairing is chosen valid, so the AI
  can never fizzle. Self-targeted AI casting (a foe guarding itself) needs
  a when-is-it-worth-it policy and stays out of scope.

## 4. Reference pack additions

- Status `venom`: no modifiers, one hook — `turn_end`, `deal_damage
  (amount 1)` — poison that ticks in the event log until it expires.
- The warren gains `hexer-1` (non-engaging hostile caster): ability
  `rockshard` (foe: `deal_damage(amount 2, spread 2)` then
  `apply_status(venom, 3)`) — at range it casts, adjacent it strikes,
  proving AI casting in exploration; as a warren local it can join pit
  battles.
- The marauder gains perk `grit` (status definition, `def +2`): the
  derived def rises 2 → 4, damage reduction 4//2 = 2 — observable in
  `--explain` provenance and in battle numbers.

## 5. What this slice proves

- Triggered effects appear in the event log and replay exactly (fold
  equivalence over a poisoned battle).
- The pipeline's provenance covers its third source kind
  (`marauder-1.stats.def --explain` shows a `(perk)` line).
- The same primitives serve casts and hooks; the same pursuit rule serves
  walking and casting foes — no parallel machinery anywhere.

## 6. Non-goals

Attacker-directed hook effects (thorns), hook-on-hook cascades, XP/leveling,
AI self-casts, resource costs (still deferred with `0004` §2), and
explored-tile memory remain out of scope.
