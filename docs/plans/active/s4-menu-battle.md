# S4 — Menu battle

The plan and record of slice S4: hostiles that wake and give chase, the mode
stack, the turn scheduler, and a menu battle with rolled initiative, `attack`,
`use`, and `flee`, ending in victory or defeat. Read it to continue S4 or to
see what was cut from v0 and why.

## Contents

- [Goal](#goal)
- [Scope](#scope)
- [Defects fixed in the port](#defects-fixed-in-the-port)
- [Progress](#progress)
- [Setup log](#setup-log)
- [Decisions](#decisions)
- [Surprises](#surprises)

## Goal

A player walks up to the bandit in the village, and a battle starts with the
initiative order in the frame. The player attacks, drinks the potion, or
flees, while the foes take their turns inside the same step. The battle ends
in victory, defeat, or escape, and the core gameplay loop is complete.

## Scope

Ported from
[v0 at `3ecc396`](https://github.com/hoelzl/glyphwright-v0/tree/3ecc396).

| Area | S4 keeps | Later |
|---|---|---|
| World | the `ai` component (`hostile`), aggression as typed state | non-hostile AI, `engages`, arenas (deferred) |
| Kernel | the mode stack, `initiative`, the scheduler (wake, chase, engage, strike), victory and defeat | interrupting focus modes, statuses and hooks in the round (deferred) |
| Combat | `strike` and initiative through the stat pipeline | abilities and `cast` (deferred) |
| Modes | `battle` with `attack`, `use`, `flee`, `look`; exploration offers only `look` after defeat | skirmish `attack` in exploration (owner decision, below) |
| Frames | a menu viewport naming the combatants (`frame/3`) | the tactics arena (deferred) |
| Harness | the `world.initiative` query path | none |
| Content | `ai` on the four hostiles, with v0's stats | `perks`, `abilities`, `arena` (deferred) |

## Defects fixed in the port

| ID | Defect | Fix |
|---|---|---|
| K8 | the scheduler docstring says the queue is area-filtered; it is not, and cross-area chasing is intended | say what the queue is |
| T1 | the fold invariant is tested tautologically, never through scheduler rounds | the grammar walks already compare whole states; they now reach battles |
| T4 | the mode-stack whitelist is a fixed list, and no walk steers toward defeat | check the stack's shape instead; add a walk that seeks defeat |
| D6 | v0 widened the `Space` protocol with `melee_range` without recording it | melee reach is derived from the geometry's own exits; the protocol stays as it is |
| D7 | battle verbs drifted from the design and the drift was never recorded | the verbs are recorded here and in the generated command reference |
| N14 | a defeat in battle prints both "You are defeated." and "You have fallen." | one message per defeat |

N14 was found while planning S4; it is not in v0's register. K3 (a flee that
resumes dialogue or lockpicking) stays in v0 with those modes.

## Progress

- [x] Plan
- [x] `ai` component and aggression; hostiles in packs and the reference world
- [x] Combat and mode events and their fold; `event/3`
- [x] Strike and initiative through the stat pipeline
- [x] The scheduler inside `step`: wake, chase, engage, battle turns, outcome
- [x] The battle mode; `attack` and `flee` in the verb table; defeat in exploration
- [x] Menu viewport in frames and the plain transcript; `frame/3`
- [x] `world.initiative` query (a new path is no new shape, so `query/2` stays)
- [x] Battle walks and a defeat-seeking walk; battle golden
- [x] Kernel, content-pack, and authoring pages; README
- [ ] Owner review of the S4 pull request
- [ ] Tag `s4`; move this plan to `docs/plans/completed/`

## Setup log

- Commits, in order: plan; `ai` component; combat and mode events
  (`event/3`); strike and initiative; menu viewport (`frame/3`); scheduler
  and battle mode; initiative query; battle and defeat walks; docs.
- New modules: `kernel/scheduler.py`, `modes/battle.py`, `effects/combat.py`.
  No new derived view: the command reference picked up `attack`, `flee`, and
  the `defeated` reason by regeneration alone.
- Goldens: `plain_battle` is new and shows a battle starting. `plain_village`
  now walks east twice, because its old walk ends next to the goblin. Both
  diffs were reviewed by eye.
- Not added: a `query/3` tag. A new query path adds no field to the payload,
  so decision 0002 does not call for a bump.

## Decisions

- **Battle is the only combat model** (owner, 2026-10-21): every hostile that
  reaches the player starts a menu battle, and exploration has no `attack`.
  v0 also had skirmishes in exploration for hostiles that did not engage; one
  rule set is smaller to test, document, and learn. The `engages` key goes.
- **Aggression and defeat are typed, not flags.** v0 kept `aggro:<id>` and
  `player-defeated` in a string-keyed flags map. In v2 a `Provoked` event sets
  the hostile's `ai.aggroed`, and the player is defeated when their hp is 0,
  which a `Defeated` event announces. The wire schema then names what each
  event carries.
- **Fleeing buys a turn, as in v0.** A flee must break melee contact, and an
  aggroed foe keeps chasing, so it can re-engage on the next turn.

## Surprises

- **Battle-only makes waking and engaging one moment.** A hostile wakes when
  the player comes within reach, which is exactly when it starts a battle, so
  chasing only happens after a flee. v0's pre-battle chase belonged to the
  skirmish model the owner cut.
- **Hostiles that act changed existing evidence.** The village golden and the
  scripted CLI session walked next to the goblin, which now starts a battle.
  The golden walks elsewhere, a separate golden covers the battle, and the
  CLI test asserts the battle.
- **Two stale texts from S3** turned up while writing these docs: the CLI's
  `--harness` help listed only `:seed` and `:frame`, and an S3 README edit
  broke the opening blockquote. Both are fixed here.
