# The kernel

How a turn is computed: the world state, commands and events, the step
function, the scheduler, modes and battle, items, and stats, plus the
checklist for adding a command or an event. Read it before you change anything under `src/glyphwright/kernel/` or
`src/glyphwright/modes/`.

## Contents

- [The model](#the-model)
- [World state](#world-state)
- [Space and entities](#space-and-entities)
- [The step contract](#the-step-contract)
- [Modes and the grammar](#modes-and-the-grammar)
- [The scheduler and battle](#the-scheduler-and-battle)
- [Items and stats](#items-and-stats)
- [Rejections](#rejections)
- [Adding a command or an event](#adding-a-command-or-an-event)

## The model

A game step is a pure function:
`step(state, command, rng) -> (state, events)`. The successor state is always
the fold of the events over the prior state (`fold` in
`src/glyphwright/kernel/state.py`), so replay from an event log and restore
from a snapshot cannot disagree. Frames are views computed from state and the
step's events; frontends are views of frames.

## World state

`WorldState` holds six fields: `entities` (id to `Entity`), `areas` (name to
`Space`), `mode_stack` (never empty; the top is the active mode), `turn`,
`rng`, the PCG64 cursor, and `initiative`, the current battle's order (empty
outside a battle). `defeated` is derived: the player is at 0 hp. The mappings are frozen at construction. Later slices
add fields with defaults, so existing constructions keep working.

## Space and entities

- **`Space`** (`src/glyphwright/world/space.py`) is one area's topology:
  `positions`, `contains`, `exits`, `passable`, and `blocked_reason`. Positions
  are `PosId`s like `village:2,1`, never screen coordinates.
- **`GridSpace`** is the one geometry so far. Its exits are the in-bounds
  neighbours, walls included: exits are topology, and `blocked_reason` says
  `wall`, `occupied`, or `edge` when a move fails.
- **`Entity`** is an id plus optional components: `position`, `actor`,
  `blocker`, `renderable`, `portal`, `ai`, and the item parts `item`,
  `consumable`, `equippable`, `inventory`, `equipment`.
- **Movement reads exits through `WorldState.exits_from`**: the space's exits
  plus the token of any portal standing on the tile, so a portal works for
  every mover. A portal may lead into another area; `move_player` then checks
  the destination in that area's space.

## The step contract

- The active mode's `handle` turns the command into events and returns the
  successor RNG cursor.
- A command that spends the turn ends its events with `TurnAdvanced`. Before
  that closing event, the scheduler gives every due foe its turn, so the
  returned events are the whole round. `step` stamps the closing event with
  the round's final RNG cursor, so the fold restores the cursor too.
- A handler that draws from the RNG without spending the turn is a bug, and
  `step` raises on it.
- Any cursor may be passed as `rng`, not only the state's own (v0 finding K1).
- A blocked move still spends the turn and says why in `MoveBlocked`.
- `look` produces no events and no turn.

## Modes and the grammar

A mode is a module with `NAME`, `VERBS`, `available_commands`, `handle`, and
`view`; `src/glyphwright/modes/__init__.py` registers them. Exploration sits
at the bottom of the stack, and a battle is pushed on top of it. The grammar a mode
returns is carried in every frame. It advertises a verb only when a command
can be formed from it, and each verb has one argument domain per argument, so
a harness can generate every valid command without knowing the rules.

Domains come in two kinds. `move` offers every exit, walls included, because
exits are topology and a failed move says why. Item verbs offer only what the
command would work on, because a pointless `use` would destroy an item for
nothing.

## The scheduler and battle

- **Outside a battle** the scheduler's queue is every hostile, in id order,
  in every area (`src/glyphwright/kernel/scheduler.py`). A hostile next to
  the player starts a battle; an aggroed one elsewhere takes one step toward
  the player over the movement graph, portals included.
- **Starting a battle** draws in the hostile, plus every hostile in the area
  that is aggroed or next to the player. It rolls initiative (d20 + `spd`),
  pushes the battle with that order, and lets every foe that outrolled the
  player strike first.
- **In a battle** (`src/glyphwright/modes/battle.py`) the player can
  `attack`, `use`, `flee`, or `look`, and each foe strikes once per round, in
  initiative order. There is no map: the frame's viewport is a `MenuView`
  naming the combatants.
- **A strike** (`src/glyphwright/effects/combat.py`) hits on d20 + `atk` >=
  10 + `def` and does 1 to `atk` damage, less `def // 2`, at least 1.
- **Endings:** the battle pops with `victory` when no foe is left, `defeat`
  when the player reaches 0 hp, and `fled` when a flee's step breaks contact
  with every foe. A fled foe stays aggroed and chases. A defeated player has
  only `look`, and every other command is rejected as `defeated`.
- **The round stops** when the mode changes or the player falls, so a hostile
  that starts a battle hands the rest of the round to it.

## Items and stats

- **Carrying:** `ItemAcquired` moves an item off the map into the actor's
  `inventory`; `ItemUsed` removes it from the world. A worn item stays in the
  inventory, and `equipment` only records its slot.
- **Stats:** `derive` in `src/glyphwright/effects/stats.py` resolves a stat as
  the actor's base value, then every additive modifier, then every
  multiplicative one, then a clamp at zero. Each step records its source and
  the running value, which `:query <id>.stats.<stat> --explain` returns.
- **Frames** carry the player's inventory, so the evidence says what is
  carried without a query.

## Rejections

Invalid input never raises; it becomes a `Rejected` value or a rejection
payload with a reason and a hint. Every reason and its hint is listed in the
generated [command reference](commands.md#rejections).

## Adding a command or an event

A new event type touches seven places, and the type checker catches a missed
`match` arm:

1. the dataclass and the `Event` union in `src/glyphwright/kernel/events.py`;
2. its arm in `apply` in `src/glyphwright/kernel/state.py`;
3. its message in `src/glyphwright/modes/messages.py`;
4. its encoding in `encode_event` in `src/glyphwright/frontends/wire.py`;
5. its fields in `_EVENT_FIELDS` in `src/glyphwright/harness/schema.py`;
6. a bumped `EVENT_SCHEMA` tag, then regenerate the schemas
   (`uv run python -m glyphwright.harness.schema`), per decision 0002;
7. a sample of it in `SAMPLES` in `tests/test_combat_events.py`, which
   checks that every event type validates on the wire.

A bumped event tag changes every recorded digest, so it is a behaviour change:
bump `RULES` and re-record the pin, as
[replay and determinism](replay-and-determinism.md#the-rules-revision-and-the-pin)
describes.

A new command needs its dataclass in the `Command` union, one `VerbSpec` row
in `VERBS` in `src/glyphwright/frontends/wire.py` (the decoder, the help
line, the rejections, and the command reference all read it), and a handler
arm and grammar entry in its mode. Then regenerate the command reference with
`uv run python -m glyphwright.harness.reference`; a test fails until you do.
