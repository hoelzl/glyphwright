# S3 — Items and stats

The plan and record of slice S3: taking, using, and equipping items, the stat
pipeline with per-modifier provenance, `:query --explain`, the inventory in
every frame, and the generated command reference. Read it to continue S3 or to
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

A player picks up the potion and the sword, drinks the potion to heal, and
equips the sword. `:query player.stats.atk --explain` shows the attack value
and every modifier that produced it. Every frame says what the player carries,
and a generated reference lists every command, rejection, and query path.

## Scope

Ported from
[v0 at `3ecc396`](https://github.com/hoelzl/glyphwright-v0/tree/3ecc396).

| Area | S3 keeps | Later |
|---|---|---|
| World | `Item`, `Consumable` (heal), `Equippable`, `Inventory`, `Equipment`, `StatModifier`, actor stats | mana, statuses, perks (deferred); AI (S4) |
| Kernel | `take`, `use`, `equip`; `ItemAcquired`, `ItemUsed`, `ItemEquipped`, `Healed` | battle `use`, death (S4) |
| Stats | the pipeline with provenance (`effects/stats.py`) | stats from statuses and perks (deferred); combat reading them (S4) |
| Harness | `:query <path> [--explain]` with structured provenance | none |
| Frames | the player's inventory (`frame/2`) | none |
| Content | `item`, `consumable`, `equippable`, actor `stats`; a potion and a sword in the village | enemy stats (S4) |
| Docs | a command reference generated from one verb table | none |

## Defects fixed in the port

| ID | Defect | Fix |
|---|---|---|
| K5 | `Healed` has no lower clamp | clamp to `0..max_hp`; refuse `heal < 1` in content. The death check comes with `ActorDied` in S4 |
| K6 | a zero-amount `Healed` would be false evidence | keep v0's rule: only restorations that land become events |
| N7 | a consumable or equippable without `item` loads, and an actor or portal could be taken | require `item`; an item is placed, and is not an actor, blocker, or portal |
| N8 | `:query` splits paths on `.`, so an id with `.` or the id `world` is unreachable | refuse both |
| N9 | v0's `--explain` returns prose, so an agent must parse text | structured provenance; plain renders the text |
| N10 | the `Healed` message says "You" for any target | a separate message for other targets |
| N11 | `use` at full hp says "you are carrying nothing usable", which is false | "nothing you carry would have an effect now" |
| N12 | a modifier `op` other than `add`/`mul`, a negative `mul`, or a stat name with `.` loads | refuse them |
| N13 | no frame says what the player carries | inventory in every frame |

N7 to N13 were found while planning S3; they are not in v0's register.

## Progress

- [ ] Plan
- [ ] Item and equipment components; actor stats
- [ ] Item events and their fold (K5); `event/2`
- [ ] Stat pipeline with provenance
- [ ] Items and stats in packs (N7, N8, N12); pack-format page
- [ ] Potion and sword in the reference world; goldens
- [ ] One verb table for the decoder, placeholders, and rejections
- [ ] `take`, `use`, `equip` in exploration (N10, N11)
- [ ] `:query --explain` with structured provenance (N9); `query/2`
- [ ] Inventory in frames and the plain transcript (N13); `frame/2`
- [ ] Item invariants in the grammar walks
- [ ] Generated command reference with a staleness test; `AGENTS.md` route
- [ ] Kernel and content-pack pages, first-pack guide, README

## Setup log

Filled in as the slice proceeds.

## Decisions

- **Inventory goes into every frame** (owner, 2026-10-21): the "semantic
  evidence first" invariant says frames are the observations, and a frame
  that cannot say what the player carries is not one.
- **Stats are provenance only in S3.** Nothing reads `atk` or `def` until
  combat in S4; `:query --explain` is what a user can do with them now.
- **Inventory is handled by exploration verbs, not a menu mode** (v0 design
  deviation D7, kept).
- **One verb table** in the wire layer drives the decoder, the plain
  placeholders, the rejection vocabulary, and the generated reference, which
  replaces three tables kept in sync by hand.

## Surprises

None yet.
