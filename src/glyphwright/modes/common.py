"""Command resolutions that more than one mode offers.

Using an item works identically while exploring and while fighting; one
resolution keeps the two modes from drifting apart.
"""

from __future__ import annotations

from glyphwright.frames.frame import GridView
from glyphwright.kernel.events import (
    Event,
    FlagSet,
    Healed,
    ItemAcquired,
    ItemUsed,
    MoveBlocked,
    Moved,
    TurnAdvanced,
)
from glyphwright.kernel.state import PLAYER, WorldState
from glyphwright.world.grid import GridSpace, _coords
from glyphwright.world.space import PosId

_TERRAIN_LEGEND: tuple[tuple[str, str], ...] = (("#", "wall"), (".", "floor"))


def legend(state: WorldState, area: str) -> tuple[tuple[str, str], ...]:
    """Terrain plus every renderable in the area: glyph vocabulary is
    content, not engine code. The unseen glyph is written last: '?' is
    reserved (the loader rejects it on renderables)."""
    entries = dict(_TERRAIN_LEGEND)
    for entity in state.entities.values():
        at = entity.at()
        if entity.renderable is None or at is None or at.area != area:
            continue
        entries[entity.renderable.glyph] = entity.renderable.label
    space = state.areas.get(area)
    if isinstance(space, GridSpace) and space.fov:
        entries["?"] = "unseen"
    return tuple(sorted(entries.items()))


def player_sight(state: WorldState) -> frozenset[PosId] | None:
    """The player's visible set in a fov-active grid area, else ``None``."""
    player_at = state.entity(PLAYER).at()
    if player_at is None:
        return None
    space = state.areas[player_at.area]
    if isinstance(space, GridSpace) and space.fov:
        return space.visible_from(player_at)
    return None


def grid_viewport(
    state: WorldState, space: GridSpace, sight: frozenset[PosId] | None
) -> GridView:
    """The one grid picture: exploration and arena battles share it."""
    glyphs = [list(row) for row in space.rows]
    if sight is not None:
        for y in range(space.height):
            for x in range(space.width):
                if space.pos(x, y) not in sight:
                    glyphs[y][x] = "?"
    # Items first, actors last: an actor standing on an item wins the tile.
    draw_order = sorted(
        state.entities.values(), key=lambda e: (e.actor is not None, e.id)
    )
    for entity in draw_order:
        at = entity.at()
        if entity.renderable is None or at is None or at.area != space.area:
            continue
        if sight is not None and at not in sight:
            continue  # beyond the light: not drawn
        x, y = _coords(at)
        glyphs[y][x] = entity.renderable.glyph
    return GridView(
        area=space.area,
        origin=(0, 0),
        tiles=tuple("".join(row) for row in glyphs),
        legend=legend(state, space.area),
    )


def witnessed(event: Event, sight: frozenset[PosId] | None) -> bool:
    """Whether the player can honestly narrate this event.

    An unseen actor's movement must not be announced by the transcript while
    the viewport and summaries conceal it; everything the player takes part
    in, and everything in the light, passes through.
    """
    if sight is None:
        return True
    if isinstance(event, Moved) and event.actor != PLAYER:
        return event.destination in sight
    return True


def move_player(state: WorldState, token: str) -> tuple[Event, ...]:
    """One player move over the movement graph; shared by every mode that
    lets the player walk (exploration and arena battles)."""
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


def cast_grammar(
    state: WorldState, foes: tuple[str, ...]
) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    """The two cast domains — castable abilities and the union of their
    targets — or ``None`` when nothing can be cast (design 0004 §2)."""
    from glyphwright.effects.abilities import TARGET_SELF, castable

    abilities = []
    targets: set[str] = set()
    for ability in castable(state, PLAYER):
        if ability.targeting == TARGET_SELF:
            abilities.append(ability.id)
            targets.add(PLAYER)
        elif foes:
            abilities.append(ability.id)
            targets.update(foes)
    if not abilities:
        return None
    return tuple(sorted(abilities)), tuple(sorted(targets))


def opened_flag(target: str) -> str:
    return f"opened:{target}"


def unlock_events(state: WorldState, target: str) -> tuple[Event, ...]:
    """A container yields: mark it open and hand over what it holds.

    Shared by the key path and the lockpick path so a chest cannot behave
    differently depending on how it was defeated.
    """
    openable = state.entity(target).openable
    assert openable is not None, "only openables reach here"
    at = state.entity(target).at()
    assert at is not None
    return (
        FlagSet(flag=opened_flag(target), value=True),
        ItemAcquired(actor=PLAYER, item=openable.contains, origin=at),
    )


def usable_items(state: WorldState) -> tuple[str, ...]:
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


def use_item(state: WorldState, item_id: str) -> tuple[Event, ...]:
    """Resolve using a carried consumable on yourself."""
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
