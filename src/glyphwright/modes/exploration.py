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
from glyphwright.kernel.commands import (
    Command,
    CommandGrammar,
    Equip,
    Look,
    Move,
    Take,
    Use,
    Wait,
)
from glyphwright.kernel.events import Event, ItemAcquired, ItemEquipped, TurnAdvanced
from glyphwright.kernel.rng import Rng
from glyphwright.kernel.state import MODE_EXPLORATION, PLAYER, WorldState
from glyphwright.modes import common, messages
from glyphwright.world.grid import GridSpace

NAME = MODE_EXPLORATION

VERBS = frozenset({"move", "look", "wait", "take", "use", "equip"})


def available_commands(state: WorldState) -> CommandGrammar:
    """Enumerate what is valid right now, drawn from real referents.

    An external harness generates valid actions from this without knowing the
    rules, which is what makes random-walk fuzzing a short test. Verbs whose
    argument domain is empty are not advertised: a grammar entry is a promise
    that a command can be formed from it.
    """
    if state.defeated:
        # A defeated player can only survey the wreckage.
        return CommandGrammar(verbs=(("look", ()),))
    at = state.entity(PLAYER).at()
    assert at is not None
    exits = tuple(sorted(state.exits_from(at)))
    verbs: list[tuple[str, tuple[tuple[str, ...], ...]]] = []
    if exits:
        verbs.append(("move", (exits,)))
    verbs.extend((("look", ()), ("wait", ())))
    for verb, domain in (
        ("take", _takeable(state)),
        ("use", common.usable_items(state)),
        ("equip", _equippable(state)),
    ):
        if domain:
            verbs.append((verb, (domain,)))
    return CommandGrammar(verbs=tuple(verbs))


def _takeable(state: WorldState) -> tuple[str, ...]:
    at = state.entity(PLAYER).at()
    if at is None:
        return ()
    return tuple(e.id for e in state.entities_at(at) if e.item is not None)


def _equippable(state: WorldState) -> tuple[str, ...]:
    player = state.entity(PLAYER)
    worn = player.equipment.equipped_items() if player.equipment else ()
    return tuple(
        item_id
        for item_id in sorted(player.carries())
        if state.entity(item_id).equippable is not None and item_id not in worn
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
            return common.move_player(state, token), rng
        case Take(item=item_id):
            return _take(state, item_id), rng
        case Use(item=item_id):
            return common.use_item(state, item_id), rng
        case Equip(item=item_id):
            return _equip(state, item_id), rng
        case _:
            raise ValueError(f"exploration cannot handle {command.verb!r}")


def _take(state: WorldState, item_id: str) -> tuple[Event, ...]:
    origin = state.entity(item_id).at()
    assert origin is not None, "the grammar only offers items lying here"
    return (
        ItemAcquired(actor=PLAYER, item=item_id, origin=origin),
        TurnAdvanced(turn=state.turn + 1),
    )


def _equip(state: WorldState, item_id: str) -> tuple[Event, ...]:
    equippable = state.entity(item_id).equippable
    assert equippable is not None, "the grammar only offers carried equippables"
    worn = state.entity(PLAYER).equipment
    replaced = worn.in_slot(equippable.slot) if worn is not None else None
    return (
        ItemEquipped(
            actor=PLAYER, item=item_id, slot=equippable.slot, replaced=replaced
        ),
        TurnAdvanced(turn=state.turn + 1),
    )


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
        inventory=common.carried(state),
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
