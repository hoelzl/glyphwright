"""Resolutions and views that more than one mode offers.

Walking and the grid picture work identically wherever the player can walk;
one implementation keeps the modes from drifting apart.
"""

from __future__ import annotations

from glyphwright.frames.frame import Cell, GridView, ItemSummary
from glyphwright.kernel.events import (
    Event,
    Healed,
    ItemUsed,
    MoveBlocked,
    Moved,
    TurnAdvanced,
)
from glyphwright.kernel.state import PLAYER, WorldState
from glyphwright.world.grid import GridSpace, coords

_TERRAIN_LEGEND: tuple[tuple[str, str], ...] = (("#", "wall"), (".", "floor"))


def legend(state: WorldState, area: str) -> tuple[tuple[str, str], ...]:
    """Terrain plus every renderable in the area: glyph vocabulary is
    content, not engine code."""
    entries = dict(_TERRAIN_LEGEND)
    for entity in state.entities.values():
        at = entity.at()
        if entity.renderable is None or at is None or at.area != area:
            continue
        entries[entity.renderable.glyph] = entity.renderable.label
    return tuple(sorted(entries.items()))


def grid_viewport(state: WorldState, space: GridSpace) -> GridView:
    """The grid picture, in tiers.

    The ground always shows through, a fixture draws on the ground, and an
    actor draws over both, so the floor persists under whoever stands on it.
    """
    cells = [[Cell(ground=ground) for ground in row] for row in space.rows]
    # Fixtures before actors: an actor standing on an item wins the top tier.
    draw_order = sorted(
        state.entities.values(), key=lambda e: (e.actor is not None, e.id)
    )
    for entity in draw_order:
        at = entity.at()
        if entity.renderable is None or at is None or at.area != space.area:
            continue
        x, y = coords(at)
        cell = cells[y][x]
        if entity.actor is not None:
            cells[y][x] = Cell(
                ground=cell.ground, fixture=cell.fixture, actor=entity.renderable.glyph
            )
        else:
            cells[y][x] = Cell(ground=cell.ground, fixture=entity.renderable.glyph)
    return GridView(
        area=space.area,
        origin=(0, 0),
        cells=tuple(tuple(row) for row in cells),
        legend=legend(state, space.area),
    )


def move_player(state: WorldState, token: str) -> tuple[Event, ...]:
    """One player move over the movement graph.

    A blocked move still spends the turn: the attempt happened, and the
    ``MoveBlocked`` event says why it failed.
    """
    origin = state.entity(PLAYER).at()
    assert origin is not None
    destination = state.exits_from(origin).get(token)
    turn = TurnAdvanced(turn=state.turn + 1)

    if destination is None or destination.area not in state.areas:
        reason: str | None = "edge"
    else:
        reason = state.areas[destination.area].blocked_reason(
            state, destination, PLAYER
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


def usable_items(state: WorldState) -> tuple[str, ...]:
    """Carried consumables that would do something now.

    Unlike the map's exits, which are topology and are offered even when
    blocked, item domains are validity filters: a use that could have no
    effect is not offered, because accepting it would destroy the item for
    nothing.
    """
    player = state.entity(PLAYER)
    actor = player.actor
    if actor is None or actor.hp >= actor.max_hp:
        return ()
    return tuple(
        item_id
        for item_id in sorted(player.carries())
        if (consumable := state.entity(item_id).consumable) is not None
        and consumable.heal > 0
    )


def use_item(state: WorldState, item_id: str) -> tuple[Event, ...]:
    """Use a carried consumable on yourself.

    The heal amount is what lands after clamping: events record what
    happened, not what was attempted, so a use never reports 0 hp.
    """
    consumable = state.entity(item_id).consumable
    actor = state.entity(PLAYER).actor
    assert consumable is not None and actor is not None
    healed = min(consumable.heal, actor.max_hp - actor.hp)
    events: list[Event] = [ItemUsed(actor=PLAYER, item=item_id, target=PLAYER)]
    if healed > 0:
        events.append(Healed(target=PLAYER, amount=healed, source=item_id))
    events.append(TurnAdvanced(turn=state.turn + 1))
    return tuple(events)


def items_here(state: WorldState) -> tuple[ItemSummary, ...]:
    """The items lying where the player stands.

    The player's glyph covers the tile, so the frame has to say what is
    under it.
    """
    at = state.entity(PLAYER).at()
    if at is None:
        return ()
    return tuple(
        ItemSummary(id=entity.id, name=entity.item.name)
        for entity in state.entities_at(at)
        if entity.item is not None
    )


def open_exits(state: WorldState) -> tuple[str, ...]:
    """The exits a player could walk through, portals included.

    The grammar offers walled exits too, so an agent can learn why a move
    fails; a reader of the frame wants the ways out. An exit someone stands
    in is still a way out, so only walls and edges are left out.
    """
    at = state.entity(PLAYER).at()
    if at is None:
        return ()
    return tuple(
        token
        for token, destination in sorted(state.exits_from(at).items())
        if destination.area in state.areas
        and state.areas[destination.area].blocked_reason(state, destination, PLAYER)
        in (None, "occupied")
    )


def why_not_usable(state: WorldState, item_id: str) -> str | None:
    """A better hint when ``use`` names a carried item that is worn instead.

    Equipment works by being equipped, which ``use`` cannot tell a player.
    """
    player = state.entity(PLAYER)
    if item_id not in player.carries():
        return None
    equippable = state.entity(item_id).equippable
    if equippable is None:
        return None
    worn = player.equipment.equipped_items() if player.equipment else ()
    if item_id in worn:
        return (
            f"{item_id} is already equipped as your {equippable.slot}; "
            "equipment works while it is worn"
        )
    return f"{item_id} is not used but equipped: equip {item_id}"


def carried(state: WorldState) -> tuple[ItemSummary, ...]:
    """The player's items in the order taken, each with its slot if worn."""
    player = state.entity(PLAYER)
    worn = (
        {item: slot for slot, item in player.equipment.slots}
        if player.equipment
        else {}
    )
    summaries = []
    for item_id in player.carries():
        item = state.entity(item_id).item
        name = item.name if item is not None else item_id
        summaries.append(ItemSummary(id=item_id, name=name, slot=worn.get(item_id)))
    return tuple(summaries)
