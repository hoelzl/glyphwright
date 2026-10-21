"""Exploration: the mode at the bottom of the stack.

A mode owns a command vocabulary, a handler, and a view. Because every mode
implements the same three functions, later modes inherit determinism, replay,
and enumeration-driven fuzzing for free.
"""

from __future__ import annotations

from glyphwright.frames.frame import (
    ActorSummary,
    PromptSpec,
    SemanticFrame,
    Viewport,
)
from glyphwright.kernel.commands import Command, CommandGrammar, Look, Move, Wait
from glyphwright.kernel.events import Event, TurnAdvanced
from glyphwright.kernel.rng import Rng
from glyphwright.kernel.state import MODE_EXPLORATION, PLAYER, WorldState
from glyphwright.modes import common, messages
from glyphwright.world.grid import GridSpace

NAME = MODE_EXPLORATION

VERBS = frozenset({"move", "look", "wait"})


def available_commands(state: WorldState) -> CommandGrammar:
    """Enumerate what is valid right now, drawn from real referents.

    An external harness generates valid actions from this without knowing the
    rules, which is what makes random-walk fuzzing a short test. Verbs whose
    argument domain is empty are not advertised: a grammar entry is a promise
    that a command can be formed from it.
    """
    at = state.entity(PLAYER).at()
    assert at is not None
    exits = tuple(sorted(state.exits_from(at)))
    verbs: list[tuple[str, tuple[tuple[str, ...], ...]]] = []
    if exits:
        verbs.append(("move", (exits,)))
    verbs.extend((("look", ()), ("wait", ())))
    return CommandGrammar(verbs=tuple(verbs))


def handle(
    state: WorldState, command: Command, rng: Rng
) -> tuple[tuple[Event, ...], Rng]:
    """Resolve one command into ordered events.

    Returns the successor RNG cursor alongside the events so that any draw a
    handler makes lands back in world state and replay resumes the stream.
    """
    match command:
        case Look():
            # An observation, not a world change: no events, no turn spent.
            return (), rng
        case Wait():
            return (TurnAdvanced(turn=state.turn + 1),), rng
        case Move(exit=token):
            return common.move_player(state, token), rng
        case _:
            raise ValueError(f"exploration cannot handle {command.verb!r}")


def view(state: WorldState, events: tuple[Event, ...]) -> SemanticFrame:
    """Project state and this turn's events into the canonical observation."""
    space = state.space_of(PLAYER)
    viewport: Viewport
    if isinstance(space, GridSpace):
        viewport = common.grid_viewport(state, space)
    else:
        raise NotImplementedError(f"no viewport for space kind: {type(space).__name__}")
    return SemanticFrame(
        turn=state.turn,
        mode=NAME,
        viewport=viewport,
        actors=_actors(state),
        messages=tuple(
            message for event in events if (message := messages.describe(event))
        ),
        prompt=PromptSpec(kind="command"),
        commands=available_commands(state),
    )


def _actors(state: WorldState) -> tuple[ActorSummary, ...]:
    """Actors in the player's current area.

    A frame discloses the here and now: no actor from another area.
    """
    player_at = state.entity(PLAYER).at()
    summaries = []
    for entity in sorted(state.entities.values(), key=lambda e: e.id):
        at = entity.at()
        if entity.actor is None or at is None:
            continue
        if player_at is not None and at.area != player_at.area:
            continue
        summaries.append(ActorSummary.of(entity, at))
    return tuple(summaries)
