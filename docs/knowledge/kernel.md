# The kernel

How a turn is computed: the world state, commands and events, the step
function, modes, and rejections, plus the checklist for adding a command or an
event. Read it before you change anything under `src/glyphwright/kernel/` or
`src/glyphwright/modes/`.

## Contents

- [The model](#the-model)
- [World state](#world-state)
- [Space and entities](#space-and-entities)
- [The step contract](#the-step-contract)
- [Modes and the grammar](#modes-and-the-grammar)
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

`WorldState` holds five fields: `entities` (id to `Entity`), `areas` (name to
`Space`), `mode_stack` (never empty; the top is the active mode), `turn`, and
`rng`, the PCG64 cursor. The mappings are frozen at construction. Later slices
add fields with defaults, so existing constructions keep working.

## Space and entities

- **`Space`** (`src/glyphwright/world/space.py`) is one area's topology:
  `positions`, `contains`, `exits`, `passable`, and `blocked_reason`. Positions
  are `PosId`s like `village:2,1`, never screen coordinates.
- **`GridSpace`** is the one geometry so far. Its exits are the in-bounds
  neighbours, walls included: exits are topology, and `blocked_reason` says
  `wall`, `occupied`, or `edge` when a move fails.
- **`Entity`** is an id plus optional components: `position`, `actor`,
  `blocker`, `renderable`. Movement reads exits through
  `WorldState.exits_from`, the single place a later exit source joins.

## The step contract

- The active mode's `handle` turns the command into events and returns the
  successor RNG cursor.
- A command that spends the turn ends its events with `TurnAdvanced`. `step`
  stamps that event with the final RNG cursor, so the fold restores the cursor
  too.
- A handler that draws from the RNG without spending the turn is a bug, and
  `step` raises on it.
- Any cursor may be passed as `rng`, not only the state's own (v0 finding K1).
- A blocked move still spends the turn and says why in `MoveBlocked`.
- `look` produces no events and no turn.

## Modes and the grammar

A mode is a module with `NAME`, `VERBS`, `available_commands`, `handle`, and
`view`; `src/glyphwright/modes/__init__.py` registers them. The grammar a mode
returns is carried in every frame. It advertises a verb only when a command
can be formed from it, and each verb has one argument domain per argument, so
a harness can generate every valid command without knowing the rules.

## Rejections

Invalid input never raises; it becomes a `Rejected` value or a rejection
payload with a reason and a hint. The engine's reasons:

| Reason | When |
|---|---|
| `wrong_mode` | the verb exists, but not in the active mode |
| `unknown_verb` | no mode knows the verb |
| `no_such_exit` | `move` names an exit that is not here |

The frontends add `unparsable` (not a command at all), `harness_disabled` (a
meta command without `--harness`), and `unknown_meta`.

## Adding a command or an event

A new event type touches six places, and the type checker catches a missed
`match` arm:

1. the dataclass and the `Event` union in `src/glyphwright/kernel/events.py`;
2. its arm in `apply` in `src/glyphwright/kernel/state.py`;
3. its message in `src/glyphwright/modes/messages.py`;
4. its encoding in `encode_event` in `src/glyphwright/frontends/wire.py`;
5. its fields in `_EVENT_FIELDS` in `src/glyphwright/harness/schema.py`;
6. a bumped `EVENT_SCHEMA` tag, then regenerate the schemas
   (`uv run python -m glyphwright.harness.schema`), per decision 0002.

A new command needs its dataclass in the `Command` union, a case in
`decode_command`, a handler arm and grammar entry in its mode, and a
rejection vocabulary entry in `src/glyphwright/api.py` if it takes
arguments.
