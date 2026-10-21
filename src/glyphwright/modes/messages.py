"""Message templates: one vocabulary of prose for every mode.

Text is generated from templates over event data, never free-written in
handlers, which keeps prose deterministic and localizable.
"""

from __future__ import annotations

from typing import assert_never

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
from glyphwright.kernel.state import PLAYER


def describe(event: Event) -> str:
    """Render one event as prose from a template. Empty string: no message."""
    match event:
        case Moved(actor=actor) if actor == PLAYER:
            return f"You go {event.exit}."
        case Moved():
            return f"{event.actor} moves {event.exit}."
        case MoveBlocked(reason="wall"):
            return f"A wall blocks the way {event.exit}."
        case MoveBlocked(reason="occupied"):
            return f"Something blocks the way {event.exit}."
        case MoveBlocked():
            return f"You cannot go {event.exit} from here."
        case ItemAcquired(actor=actor) if actor == PLAYER:
            return f"You take {event.item}."
        case ItemAcquired():
            return f"{event.actor} takes {event.item}."
        case ItemUsed(actor=actor) if actor == PLAYER:
            return f"You use {event.item}."
        case ItemUsed():
            return f"{event.actor} uses {event.item}."
        case ItemEquipped(actor=actor, replaced=None) if actor == PLAYER:
            return f"You equip {event.item}."
        case ItemEquipped(actor=actor) if actor == PLAYER:
            return f"You equip {event.item}, putting away {event.replaced}."
        case ItemEquipped():
            return f"{event.actor} equips {event.item}."
        case Healed(target=target) if target == PLAYER:
            return f"You recover {event.amount} hp."
        case Healed():
            # v2 finding N10: v0 said "You" whoever was healed.
            return f"{event.target} recovers {event.amount} hp."
        case TurnAdvanced():
            return ""
        case _:
            assert_never(event)
