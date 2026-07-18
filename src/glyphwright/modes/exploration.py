"""Exploration: the mode at the bottom of the stack.

A mode owns a command vocabulary, a handler, and a view. Because every mode
implements the same three methods, later modes (battle, dialogue, minigames)
inherit determinism, replay, and enumeration-driven fuzzing for free (design
0003 section 10).
"""

from __future__ import annotations

from glyphwright.effects.combat import (
    hostile_actors,
    melee_adjacent,
    provoke,
    strike,
)
from glyphwright.frames.frame import (
    ActorSummary,
    PromptSpec,
    RoomView,
    SemanticFrame,
    Viewport,
)
from glyphwright.kernel.commands import (
    Attack,
    Cast,
    Command,
    CommandGrammar,
    Equip,
    Look,
    Move,
    Open,
    Take,
    Talk,
    Use,
    Wait,
)
from glyphwright.kernel.events import (
    PLAYER_DEFEATED,
    Event,
    ItemAcquired,
    ItemEquipped,
    ItemUsed,
    Moved,
    TurnAdvanced,
)
from glyphwright.kernel.rng import Rng
from glyphwright.kernel.state import MODE_EXPLORATION, PLAYER, WorldState, fold
from glyphwright.modes import common, messages
from glyphwright.world.entities import Equipment
from glyphwright.world.grid import GridSpace
from glyphwright.world.roomgraph import RoomGraphSpace
from glyphwright.world.space import PosId

NAME = MODE_EXPLORATION

VERBS = frozenset(
    {"move", "look", "wait", "take", "use", "equip", "attack", "talk", "open", "cast"}
)


def _all_exits(state: WorldState, pos: PosId) -> dict[str, PosId]:
    """``move <exit-token>`` is the only movement command, everywhere — a door
    to another area is simply one more token (0003 §7.4)."""
    return state.exits_from(pos)


def _takeable(state: WorldState) -> tuple[str, ...]:
    at = state.entity(PLAYER).at()
    if at is None:
        return ()
    return tuple(
        entity.id for entity in state.entities_at(at) if entity.item is not None
    )


def _usable(state: WorldState) -> tuple[str, ...]:
    return common.usable_items(state)


def _attackable(state: WorldState) -> tuple[str, ...]:
    """Adjacent hostiles. Exploration combat is melee: the attack range is one
    exit, and anything farther must be closed with first. Ranged attacks
    arrive with abilities."""
    player_at = state.entity(PLAYER).at()
    if player_at is None:
        return ()
    space = state.areas[player_at.area]
    return tuple(
        entity.id
        for entity in hostile_actors(state)
        if (at := entity.at()) is not None and melee_adjacent(space, player_at, at)
    )


def _in_reach(state: WorldState) -> tuple[str, ...]:
    """Entity ids within the geometry's striking distance of the player."""
    player_at = state.entity(PLAYER).at()
    if player_at is None:
        return ()
    space = state.areas[player_at.area]
    return tuple(
        sorted(
            entity.id
            for entity in state.entities.values()
            if entity.id != PLAYER
            and (at := entity.at()) is not None
            and at.area == player_at.area
            and melee_adjacent(space, player_at, at)
        )
    )


def _speakers(state: WorldState) -> tuple[str, ...]:
    return tuple(
        entity_id
        for entity_id in _in_reach(state)
        if state.entity(entity_id).dialogue is not None
    )


def _openable(state: WorldState) -> tuple[str, ...]:
    return tuple(
        entity_id
        for entity_id in _in_reach(state)
        if state.entity(entity_id).openable is not None
        and not state.flags.get(common.opened_flag(entity_id))
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
    if state.flags.get(PLAYER_DEFEATED):
        # A defeated protagonist can only survey the wreckage.
        return CommandGrammar(verbs=(("look", ()),))
    at = state.entity(PLAYER).at()
    assert at is not None
    exits = tuple(sorted(_all_exits(state, at)))
    verbs: list[tuple[str, tuple[tuple[str, ...], ...]]] = []
    if exits:
        verbs.append(("move", (exits,)))
    verbs.extend((("look", ()), ("wait", ())))
    for verb, domain in (
        ("take", _takeable(state)),
        ("use", _usable(state)),
        ("equip", _equippable(state)),
        ("attack", _attackable(state)),
        ("talk", _speakers(state)),
        ("open", _openable(state)),
    ):
        if domain:
            verbs.append((verb, (domain,)))
    cast_domains = common.cast_grammar(state, _attackable(state))
    if cast_domains is not None:
        verbs.append(("cast", cast_domains))
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
        case Take(item=item_id):
            return _take(state, item_id), rng
        case Use(item=item_id):
            return common.use_item(state, item_id), rng
        case Equip(item=item_id):
            return _equip(state, item_id), rng
        case Attack(target=target_id):
            return _attack(state, target_id, rng)
        case Talk(target=target_id):
            from glyphwright.modes import dialogue

            return (
                *dialogue.open_events(state, target_id),
                TurnAdvanced(turn=state.turn + 1),
            ), rng
        case Open(target=target_id):
            return _open(state, target_id), rng
        case Cast(ability=ability_id, target=target_id):
            from glyphwright.effects.abilities import cast_events

            return cast_events(
                state, PLAYER, ability_id, target_id, _attackable(state), rng
            )
        case _:
            raise ValueError(f"exploration cannot handle {command.verb!r}")


def _open(state: WorldState, target_id: str) -> tuple[Event, ...]:
    from glyphwright.modes import lockpick

    openable = state.entity(target_id).openable
    assert openable is not None, "the grammar only offers openables"
    carried = state.entity(PLAYER).carries()
    if openable.key is not None and openable.key in carried:
        # The honest way in: the key opens it outright, and the transcript
        # says so — a silent open is indistinguishable from a bug.
        return (
            ItemUsed(actor=PLAYER, item=openable.key, target=target_id, consumed=False),
            *common.unlock_events(state, target_id),
            TurnAdvanced(turn=state.turn + 1),
        )
    return (
        *lockpick.open_events(state, target_id),
        TurnAdvanced(turn=state.turn + 1),
    )


def _take(state: WorldState, item_id: str) -> tuple[Event, ...]:
    origin = state.entity(item_id).at()
    assert origin is not None, "the grammar only offers items lying here"
    return (
        ItemAcquired(actor=PLAYER, item=item_id, origin=origin),
        TurnAdvanced(turn=state.turn + 1),
    )


def _attack(
    state: WorldState, target_id: str, rng: Rng
) -> tuple[tuple[Event, ...], Rng]:
    struck, rng = strike(state, PLAYER, target_id, rng)
    # Being struck is provocation, recorded as a flag so it replays — but only
    # a survivor can be provoked; a corpse does not snarl.
    events: list[Event] = [
        *struck,
        *provoke(fold(state, struck), target_id),
        TurnAdvanced(turn=state.turn + 1),
    ]
    return tuple(events), rng


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
    """Project state and this turn's events into the canonical observation.

    One visible set serves the viewport, the actor summaries, and the message
    filter, so every part of a frame tells the same truth (design 0006 §1).
    """
    space = state.space_of(PLAYER)
    sight = common.player_sight(state)
    viewport: Viewport
    if isinstance(space, GridSpace):
        viewport = common.grid_viewport(state, space, sight)
    elif isinstance(space, RoomGraphSpace):
        viewport = _room_viewport(state, space)
    else:
        raise NotImplementedError(f"no viewport for space kind: {type(space).__name__}")
    return SemanticFrame(
        turn=state.turn,
        mode=NAME,
        viewport=viewport,
        actors=_actors(state, sight),
        messages=tuple(
            message
            for event in events
            if _witnessed(state, event, sight) and (message := messages.describe(event))
        ),
        prompt=PromptSpec(kind="command"),
        commands=available_commands(state),
    )


def _witnessed(state: WorldState, event: Event, sight: frozenset[PosId] | None) -> bool:
    """Whether the player can honestly narrate this event.

    An unseen hostile's movement must not be announced by the transcript
    while the viewport and summaries conceal it; everything the player takes
    part in, and everything in the light, passes through.
    """
    if sight is None:
        return True
    if isinstance(event, Moved) and event.actor != PLAYER:
        return event.destination in sight
    return True


def _room_viewport(state: WorldState, space: RoomGraphSpace) -> RoomView:
    at = state.entity(PLAYER).at()
    assert at is not None
    room = space.room(at)
    contents = tuple(
        entity.id
        for entity in state.entities_at(at)
        if entity.id != PLAYER
        and (
            entity.item is not None
            or entity.actor is not None
            or entity.openable is not None
        )
    )
    return RoomView(
        area=space.area,
        room=room.id,
        name=room.name,
        description=room.description,
        contents=contents,
        exits=tuple(sorted(_all_exits(state, at))),
    )


def _actors(
    state: WorldState, sight: frozenset[PosId] | None
) -> tuple[ActorSummary, ...]:
    """Visible actors in the player's current area.

    A frame discloses the here and now: no actor from another area, and in a
    fov-active area none beyond the light — a harness reads the same truth
    the player sees (design 0006 §1). The oracle remains the x-ray.
    """
    player_at = state.entity(PLAYER).at()
    summaries = []
    for entity in sorted(state.entities.values(), key=lambda e: e.id):
        at = entity.at()
        if entity.actor is None or at is None:
            continue
        if player_at is not None and at.area != player_at.area:
            continue
        if sight is not None and entity.id != PLAYER and at not in sight:
            continue  # beyond the light
        summaries.append(
            ActorSummary(
                id=entity.id,
                name=entity.actor.name,
                hp=entity.actor.hp,
                max_hp=entity.actor.max_hp,
                at=at,
                statuses=entity.statuses.ids() if entity.statuses else (),
            )
        )
    return tuple(summaries)
