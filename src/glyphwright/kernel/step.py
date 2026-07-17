"""The transition function: the whole simulation, as one pure function.

No I/O, no wall clock, no ambient globals. All engine behavior happens inside
``step`` (design 0003 section 5.1).
"""

from __future__ import annotations

from dataclasses import replace

from glyphwright.kernel.commands import Command
from glyphwright.kernel.events import Event
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
    """
    if state.mode != exploration.NAME:
        raise ValueError(f"unknown mode: {state.mode}")

    events, next_rng = exploration.handle(state, command, rng)
    next_state = fold(state, events)
    return replace(next_state, rng=next_rng), events
