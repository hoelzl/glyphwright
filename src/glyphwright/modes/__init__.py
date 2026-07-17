"""The mode registry: engine control flow is a pushdown automaton of modes.

Every mode implements ``available_commands``, ``handle``, and ``view``
(design 0003 §10); the active mode is named by the top of the state's mode
stack. Modes are modules satisfying the :class:`Mode` protocol structurally.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol, cast

from glyphwright.modes import battle, exploration

if TYPE_CHECKING:
    from glyphwright.frames.frame import SemanticFrame
    from glyphwright.kernel.commands import Command, CommandGrammar
    from glyphwright.kernel.events import Event
    from glyphwright.kernel.rng import Rng
    from glyphwright.kernel.state import WorldState


class Mode(Protocol):
    """What every mode module provides (0003 §10).

    ``VERBS`` is the mode's full verb vocabulary — a superset of any one
    frame's grammar — so a rejection can distinguish "not a thing you do in
    this mode" from "nothing to do it to right now".
    """

    NAME: str
    VERBS: frozenset[str]
    available_commands: Callable[[WorldState], CommandGrammar]
    handle: Callable[[WorldState, Command, Rng], tuple[tuple[Event, ...], Rng]]
    view: Callable[[WorldState, tuple[Event, ...]], SemanticFrame]


# Modules satisfy the protocol structurally; the casts are for mypy, which
# does not narrow ModuleType against Protocols with callable attributes.
_MODES: dict[str, Mode] = {
    exploration.NAME: cast(Mode, exploration),
    battle.NAME: cast(Mode, battle),
}


def active(state: WorldState) -> Mode:
    """The module implementing the state's active mode."""
    try:
        return _MODES[state.mode]
    except KeyError as error:
        raise ValueError(f"unknown mode: {state.mode}") from error
