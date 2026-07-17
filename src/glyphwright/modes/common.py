"""Command resolutions that more than one mode offers.

Using an item works identically while exploring and while fighting; one
resolution keeps the two modes from drifting apart.
"""

from __future__ import annotations

from glyphwright.kernel.events import Event, Healed, ItemUsed, TurnAdvanced
from glyphwright.kernel.state import PLAYER, WorldState


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
