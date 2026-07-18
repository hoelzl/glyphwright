"""The transition function: the whole simulation, as one pure function.

No I/O, no wall clock, no ambient globals. All engine behavior happens inside
``step`` (design 0003 section 5.1).
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

    A command that spends the turn hands control to the scheduler before the
    turn closes: AI actors take their turns inside this same step (0003 §5.5),
    so the returned events are the whole round — player first, then AI, then
    any battle outcome, then ``TurnAdvanced``. The closing ``TurnAdvanced`` is
    stamped with the round's final RNG cursor, which is what keeps the
    successor state — cursor included — exactly the fold of the events
    (0003 §5.3). A handler that draws without spending the turn would break
    that bookkeeping, so it is forbidden and enforced here.
    """
    events, next_rng = modes.active(state).handle(state, command, rng)
    next_state = fold(state, events)

    if events and isinstance(events[-1], TurnAdvanced):
        ai_events, next_state, next_rng = scheduler.run(
            next_state, next_rng, prior=events
        )
        closing = replace(events[-1], rng=next_rng.encode())
        events = (*events[:-1], *ai_events, closing)
        return apply(next_state, closing), events

    if next_rng != state.rng:
        raise AssertionError(
            "a handler drew from the RNG without spending the turn; "
            "the draw would escape the event fold"
        )
    return next_state, events
