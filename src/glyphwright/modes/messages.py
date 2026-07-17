"""Message templates: one vocabulary of prose for every mode.

Text is generated from templates over event data, never free-written in
handlers, which keeps prose deterministic and localizable (design 0003 §11).
"""

from __future__ import annotations

from glyphwright.kernel.events import (
    PLAYER_DEFEATED,
    ActorDied,
    AttackMissed,
    ChoiceOffered,
    DamageDealt,
    DialogueLine,
    Event,
    FlagSet,
    FleeFailed,
    FocusSet,
    Healed,
    ItemAcquired,
    ItemEquipped,
    ItemUsed,
    MinigameResolved,
    ModePopped,
    ModePushed,
    MoveBlocked,
    Moved,
    PinSet,
    PinSlipped,
    TurnAdvanced,
    aggro_subject,
)
from glyphwright.kernel.state import MODE_BATTLE, MODE_LOCKPICK, PLAYER


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
        case ModePushed(mode=mode) if mode == MODE_LOCKPICK:
            return "You bend to the lock."
        case ModePushed():
            return ""
        case ModePopped(outcome="victory"):
            return "You are victorious!"
        case ModePopped(outcome="defeat"):
            return "You have fallen."
        case ModePopped(outcome="fled"):
            return "You break away and flee!"
        case ModePopped(outcome="done"):
            return "You end the conversation."
        case ModePopped(outcome="abandoned"):
            return "You step back from the lock."
        case ModePopped():
            return ""
        case FleeFailed():
            return "There is no way out!"
        case DialogueLine() | ChoiceOffered() | FocusSet():
            # The dialogue viewport already carries speaker, line, and
            # choices; a message copy would print every line twice.
            return ""
        case PinSet():
            return "A pin clicks into place."
        case PinSlipped():
            return "The pick slips and the pins reset."
        case MinigameResolved(outcome="opened"):
            return "The lock springs open!"
        case MinigameResolved():
            return ""
        case TurnAdvanced():
            return ""
