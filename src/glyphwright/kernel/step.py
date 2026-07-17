"""The transition function: the whole simulation, as one pure function.

No I/O, no wall clock, no ambient globals. All engine behavior happens inside
``step`` (design 0003 section 5.1).
"""

from __future__ import annotations

from dataclasses import replace

from glyphwright.kernel import scheduler
from glyphwright.kernel.commands import Command
from glyphwright.kernel.events import Event, TurnAdvanced
from glyphwright.kernel.rng import Rng
from glyphwright.kernel.state import WorldState, fold
from glyphwright.modes import exploration


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
    ``TurnAdvanced``.
    """
    if state.mode != exploration.NAME:
        raise ValueError(f"unknown mode: {state.mode}")

    events, next_rng = exploration.handle(state, command, rng)
    next_state = fold(state, events)

    if events and isinstance(events[-1], TurnAdvanced):
        ai_events, next_rng = scheduler.run(next_state, next_rng)
        next_state = fold(next_state, ai_events)
        events = (*events[:-1], *ai_events, events[-1])

    return replace(next_state, rng=next_rng), events
