"""Message templates: one vocabulary of prose for every mode.

Text is generated from templates over event data, never free-written in
handlers, which keeps prose deterministic and localizable (design 0003 §11).
"""

from __future__ import annotations

from glyphwright.kernel.events import (
    PLAYER_DEFEATED,
    ActorDied,
    AttackMissed,
    DamageDealt,
    Event,
    FlagSet,
    FleeFailed,
    Healed,
    ItemAcquired,
    ItemEquipped,
    ItemUsed,
    ModePopped,
    ModePushed,
    MoveBlocked,
    Moved,
    TurnAdvanced,
    aggro_subject,
)
from glyphwright.kernel.state import MODE_BATTLE, PLAYER


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
        case DamageDealt(source=source) if source == PLAYER:
            return f"You strike {event.target} for {event.amount} damage."
        case DamageDealt(target=target) if target == PLAYER:
            return f"{event.source} hits you for {event.amount} damage."
        case DamageDealt():
            return f"{event.source} strikes {event.target} for {event.amount} damage."
        case AttackMissed(source=source) if source == PLAYER:
            return f"You miss {event.target}."
        case AttackMissed():
            return f"{event.source} lunges and misses."
        case ActorDied():
            return f"{event.actor} dies."
        case FlagSet(flag=flag) if aggro_subject(flag) is not None:
            return f"{aggro_subject(flag)} snarls and turns on you!"
        case FlagSet(flag=flag) if flag == PLAYER_DEFEATED:
            return "You are defeated."
        case FlagSet():
            return ""
        case ModePushed(mode=mode) if mode == MODE_BATTLE:
            return "Battle is joined!"
        case ModePushed():
            return ""
        case ModePopped(outcome="victory"):
            return "You are victorious!"
        case ModePopped(outcome="defeat"):
            return "You have fallen."
        case ModePopped(outcome="fled"):
            return "You break away and flee!"
        case ModePopped():
            return ""
        case FleeFailed():
            return "There is no way out!"
        case TurnAdvanced():
            return ""
