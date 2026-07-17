"""Command resolutions that more than one mode offers.

Using an item works identically while exploring and while fighting; one
resolution keeps the two modes from drifting apart.
"""

from __future__ import annotations

from glyphwright.kernel.events import (
    Event,
    FlagSet,
    Healed,
    ItemAcquired,
    ItemUsed,
    TurnAdvanced,
)
from glyphwright.kernel.state import PLAYER, WorldState


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
