"""Exploration: the mode at the bottom of the stack.

A mode owns a command vocabulary, a handler, and a view. Because every mode
implements the same three methods, later modes (battle, dialogue, minigames)
inherit determinism, replay, and enumeration-driven fuzzing for free (design
0003 section 10).
"""

from __future__ import annotations

from glyphwright.frames.frame import ActorSummary, GridView, PromptSpec, SemanticFrame
from glyphwright.kernel.commands import Command, CommandGrammar, Look, Move, Wait
from glyphwright.kernel.events import Event, MoveBlocked, Moved, TurnAdvanced
from glyphwright.kernel.rng import Rng
from glyphwright.kernel.state import PLAYER, WorldState
from glyphwright.world.grid import GridSpace

NAME = "exploration"

_LEGEND: tuple[tuple[str, str], ...] = (
    ("@", "player"),
    ("#", "wall"),
    (".", "floor"),
)


def available_commands(state: WorldState) -> CommandGrammar:
    """Enumerate what is valid right now, drawn from real referents.

    An external harness generates valid actions from this without knowing the
    rules, which is what makes random-walk fuzzing a short test.
    """
    space = state.space_of(PLAYER)
    at = state.entity(PLAYER).at()
    assert at is not None  # space_of would have raised
    exits = tuple(sorted(space.exits(at)))
    return CommandGrammar(
        verbs=(
            ("move", (exits,)),
            ("look", ()),
            ("wait", ()),
        )
    )


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
            return _move(state, token), rng


def _move(state: WorldState, token: str) -> tuple[Event, ...]:
    space = state.space_of(PLAYER)
    origin = state.entity(PLAYER).at()
    assert origin is not None
    destination = space.exits(origin).get(token)
    turn = TurnAdvanced(turn=state.turn + 1)

    # An exit token outside the area's topology never reaches the kernel: it is
    # absent from the grammar, so the API rejects it before a turn is spent.
    reason = (
        "edge"
        if destination is None
        else space.blocked_reason(state, destination, PLAYER)
    )
    if destination is None or reason is not None:
        return (
            MoveBlocked(
                actor=PLAYER, origin=origin, exit=token, reason=reason or "edge"
            ),
            turn,
        )
    return (
        Moved(actor=PLAYER, origin=origin, destination=destination, exit=token),
        turn,
    )


def view(state: WorldState, events: tuple[Event, ...]) -> SemanticFrame:
    """Project state and this turn's events into the canonical observation."""
    space = state.space_of(PLAYER)
    if not isinstance(space, GridSpace):
        # RoomView arrives with RoomGraphSpace in slice 4 (0003 sections 7.3, 18).
        raise NotImplementedError(f"no viewport for space kind: {type(space).__name__}")
    return SemanticFrame(
        turn=state.turn,
        mode=NAME,
        viewport=_viewport(state, space),
        actors=_actors(state),
        messages=tuple(message for event in events if (message := describe(event))),
        prompt=PromptSpec(kind="command"),
        commands=available_commands(state),
    )


def _viewport(state: WorldState, space: GridSpace) -> GridView:
    glyphs = [list(row) for row in space.rows]
    for entity in sorted(state.entities.values(), key=lambda e: e.id):
        at = entity.at()
        if entity.renderable is None or at is None or at.area != space.area:
            continue
        from glyphwright.world.grid import _coords

        x, y = _coords(at)
        glyphs[y][x] = entity.renderable.glyph
    return GridView(
        area=space.area,
        origin=(0, 0),
        tiles=tuple("".join(row) for row in glyphs),
        legend=_LEGEND,
    )


def _actors(state: WorldState) -> tuple[ActorSummary, ...]:
    summaries = []
    for entity in sorted(state.entities.values(), key=lambda e: e.id):
        at = entity.at()
        if entity.actor is None or at is None:
            continue
        summaries.append(
            ActorSummary(
                id=entity.id,
                name=entity.actor.name,
                hp=entity.actor.hp,
                max_hp=entity.actor.max_hp,
                at=at,
            )
        )
    return tuple(summaries)


def describe(event: Event) -> str:
    """Render one event as prose from a template, never free-written text."""
    match event:
        case Moved():
            return f"You go {event.exit}."
        case MoveBlocked(reason="wall"):
            return f"A wall blocks the way {event.exit}."
        case MoveBlocked(reason="occupied"):
            return f"Something blocks the way {event.exit}."
        case MoveBlocked():
            return f"You cannot go {event.exit} from here."
        case TurnAdvanced():
            return ""
