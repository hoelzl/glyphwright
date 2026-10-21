"""Resolutions and views that more than one mode offers.

Walking and the grid picture work identically wherever the player can walk;
one implementation keeps the modes from drifting apart.
"""

from __future__ import annotations

from glyphwright.frames.frame import Cell, GridView
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
