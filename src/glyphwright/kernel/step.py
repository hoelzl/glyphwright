"""The transition function: the whole simulation, as one pure function.

No I/O, no wall clock, no ambient globals. All engine behavior happens inside
``step``.
"""

from __future__ import annotations

from dataclasses import replace

from glyphwright import modes
from glyphwright.kernel import scheduler
from glyphwright.kernel.commands import Command
from glyphwright.kernel.events import Event, TurnAdvanced
from glyphwright.kernel.rng import Rng
from glyphwright.kernel.state import WorldState, apply, fold


def step(
    state: WorldState, command: Command, rng: Rng
) -> tuple[WorldState, tuple[Event, ...]]:
    """Apply one command, returning the successor state and ordered events.

    The command must already be valid for the active mode; validity is a
    question the caller answers against the frame's command grammar, and an
    invalid command is a typed rejection rather than a step.

    ``rng`` is the cursor the round draws from; any cursor is allowed, not only
    the state's own. A command that spends the turn ends with ``TurnAdvanced``,
    and that closing event is stamped with the round's final cursor, which
    keeps the successor state, cursor included, exactly the fold of the
    events. A handler that draws without spending the turn would break that
    bookkeeping, so it is forbidden and enforced here.
    """
    events, next_rng = modes.active(state).handle(state, command, rng)

    if events and isinstance(events[-1], TurnAdvanced):
        # The foes act between the player's events and the closing
        # TurnAdvanced, so the returned events are the whole round.
        next_state = fold(state, events[:-1])
        foe_events, next_state, next_rng = scheduler.run(next_state, next_rng)
        closing = replace(events[-1], rng=next_rng.encode())
        return apply(next_state, closing), (*events[:-1], *foe_events, closing)

    next_state = fold(state, events)

    # v0 compared against state.rng here (finding K1), which made stepping
    # with any other cursor raise even when nothing was drawn.
    if next_rng != rng:
        raise AssertionError(
            "a handler drew from the RNG without spending the turn; "
            "the draw would escape the event fold"
        )
    return next_state, events
