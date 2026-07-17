"""Exploration: the mode at the bottom of the stack.

A mode owns a command vocabulary, a handler, and a view. Because every mode
implements the same three methods, later modes (battle, dialogue, minigames)
inherit determinism, replay, and enumeration-driven fuzzing for free (design
0003 section 10).
"""

from __future__ import annotations

from glyphwright.frames.frame import ActorSummary, GridView, PromptSpec, SemanticFrame
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
from glyphwright.kernel.events import (
    Event,
    Healed,
    ItemAcquired,
    ItemEquipped,
    ItemUsed,
    MoveBlocked,
    Moved,
    TurnAdvanced,
)
from glyphwright.kernel.rng import Rng
from glyphwright.kernel.state import PLAYER, WorldState
from glyphwright.world.entities import Equipment
from glyphwright.world.grid import GridSpace

NAME = "exploration"

# The single source of glyph knowledge: frames carry it, and the plain
# frontend's parser derives its tile character set from it.
LEGEND: tuple[tuple[str, str], ...] = (
    ("@", "player"),
    ("#", "wall"),
    (".", "floor"),
    ("!", "potion"),
    ("/", "weapon"),
)


def _takeable(state: WorldState) -> tuple[str, ...]:
    at = state.entity(PLAYER).at()
    if at is None:
        return ()
    return tuple(
        entity.id for entity in state.entities_at(at) if entity.item is not None
    )


def _usable(state: WorldState) -> tuple[str, ...]:
    """Carried consumables that would currently do something.

    Unlike the map's exits — topology, enumerable even when blocked — item
    domains are validity filters, and a use that can have no effect is not
    offered: accepting it would destroy the item for nothing.
    """
    player = state.entity(PLAYER)
    if player.actor is None or player.actor.hp >= player.actor.max_hp:
        return ()
    return tuple(
        item_id
        for item_id in sorted(player.carries())
        if (consumable := state.entity(item_id).consumable) is not None
        and consumable.heal > 0
    )


def _equippable(state: WorldState) -> tuple[str, ...]:
    player = state.entity(PLAYER)
    worn = (player.equipment or Equipment()).equipped_items()
    return tuple(
        item_id
        for item_id in sorted(player.carries())
        if state.entity(item_id).equippable is not None and item_id not in worn
    )


def available_commands(state: WorldState) -> CommandGrammar:
    """Enumerate what is valid right now, drawn from real referents.

    An external harness generates valid actions from this without knowing the
    rules, which is what makes random-walk fuzzing a short test. Verbs whose
    argument domain is empty are not advertised: a grammar entry is a promise
    that a command can be formed from it.
    """
    space = state.space_of(PLAYER)
    at = state.entity(PLAYER).at()
    assert at is not None  # space_of would have raised
    exits = tuple(sorted(space.exits(at)))
    verbs: list[tuple[str, tuple[tuple[str, ...], ...]]] = []
    if exits:
        verbs.append(("move", (exits,)))
    verbs.extend((("look", ()), ("wait", ())))
    for verb, domain in (
        ("take", _takeable(state)),
        ("use", _usable(state)),
        ("equip", _equippable(state)),
    ):
        if domain:
            verbs.append((verb, (domain,)))
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
            return _move(state, token), rng
        case Take(item=item_id):
            return _take(state, item_id), rng
        case Use(item=item_id):
            return _use(state, item_id), rng
        case Equip(item=item_id):
            return _equip(state, item_id), rng


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


def _take(state: WorldState, item_id: str) -> tuple[Event, ...]:
    origin = state.entity(item_id).at()
    assert origin is not None, "the grammar only offers items lying here"
    return (
        ItemAcquired(actor=PLAYER, item=item_id, origin=origin),
        TurnAdvanced(turn=state.turn + 1),
    )


def _use(state: WorldState, item_id: str) -> tuple[Event, ...]:
    consumable = state.entity(item_id).consumable
    assert consumable is not None, "the grammar only offers carried consumables"
    actor = state.entity(PLAYER).actor
    assert actor is not None
    healed = min(consumable.heal, actor.max_hp - actor.hp)
    return (
        ItemUsed(actor=PLAYER, item=item_id, target=PLAYER, consumed=True),
        Healed(target=PLAYER, amount=healed, source=item_id),
        TurnAdvanced(turn=state.turn + 1),
    )


def _equip(state: WorldState, item_id: str) -> tuple[Event, ...]:
    equippable = state.entity(item_id).equippable
    assert equippable is not None, "the grammar only offers carried equippables"
    worn = state.entity(PLAYER).equipment or Equipment()
    return (
        ItemEquipped(
            actor=PLAYER,
            item=item_id,
            slot=equippable.slot,
            replaced=worn.in_slot(equippable.slot),
        ),
        TurnAdvanced(turn=state.turn + 1),
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
    # Items first, actors last: an actor standing on an item wins the tile,
    # whatever the ids happen to sort like. Ties within a layer stay id-sorted.
    draw_order = sorted(
        state.entities.values(), key=lambda e: (e.actor is not None, e.id)
    )
    for entity in draw_order:
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
        legend=LEGEND,
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
        case ItemAcquired():
            return f"You take {event.item}."
        case ItemUsed():
            return f"You use {event.item}."
        case ItemEquipped(replaced=None):
            return f"You equip {event.item}."
        case ItemEquipped():
            return f"You equip {event.item}, putting away {event.replaced}."
        case Healed():
            return f"You recover {event.amount} hp."
        case TurnAdvanced():
            return ""
