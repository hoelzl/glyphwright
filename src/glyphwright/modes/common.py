"""Command resolutions that more than one mode offers.

Using an item works identically while exploring and while fighting; one
resolution keeps the two modes from drifting apart.
"""

from __future__ import annotations

from glyphwright.frames.frame import Cell, GridView
from glyphwright.kernel.events import (
    Event,
    FlagSet,
    Healed,
    ItemAcquired,
    ItemUsed,
    ManaRestored,
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
    """The one grid picture: exploration and arena battles share it.

    Cells are tiered (design 0012 §4): the ground always shows through, a
    fixture (item, portal) draws on the ground, and an actor draws over both
    — so the floor persists under whoever stands on it.
    """
    cells: list[list[Cell]] = []
    for y in range(space.height):
        row = []
        for x in range(space.width):
            seen = sight is None or space.pos(x, y) in sight
            row.append(Cell(ground=space.rows[y][x] if seen else "?"))
        cells.append(row)
    # Fixtures before actors: an actor standing on an item wins the top tier.
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
    offered: accepting it would destroy the item for nothing. A consumable
    counts when any of its restorations would land (heal against a wound,
    mana against a spent pool — design 0009 §3).
    """
    player = state.entity(PLAYER)
    actor = player.actor
    if actor is None:
        return ()
    wounded = actor.hp < actor.max_hp
    spent = actor.mp < actor.max_mp
    return tuple(
        item_id
        for item_id in sorted(player.carries())
        if (consumable := state.entity(item_id).consumable) is not None
        and ((consumable.heal > 0 and wounded) or (consumable.mana > 0 and spent))
    )


def use_item(state: WorldState, item_id: str) -> tuple[Event, ...]:
    """Resolve using a carried consumable on yourself.

    Amounts are post-clamp: events record what landed, not what was
    attempted.
    """
    consumable = state.entity(item_id).consumable
    assert consumable is not None, "the grammar only offers carried consumables"
    actor = state.entity(PLAYER).actor
    assert actor is not None
    events: list[Event] = [
        ItemUsed(actor=PLAYER, item=item_id, target=PLAYER, consumed=True)
    ]
    # Only restorations that actually land become events: a dual elixir used
    # at full hp must not record a zero-amount Healed — events are evidence
    # of what happened, and "You recover 0 hp." is not a thing that happened.
    healed = min(consumable.heal, actor.max_hp - actor.hp)
    if healed > 0:
        events.append(Healed(target=PLAYER, amount=healed, source=item_id))
    restored = min(consumable.mana, actor.max_mp - actor.mp)
    if restored > 0:
        events.append(ManaRestored(target=PLAYER, amount=restored, source=item_id))
    events.append(TurnAdvanced(turn=state.turn + 1))
    return tuple(events)
