"""Wire encoding: the actual interoperability contract.

With no shared Python types across the verification boundary, these JSON
encodings — not the dataclasses — are what an external adapter consumes. Every
frame and event carries a schema tag so the contract cannot drift silently
(design 0003 section 15, ADR-006).
"""

from __future__ import annotations

from typing import Any

from glyphwright.frames.frame import SemanticFrame
from glyphwright.kernel.commands import (
    Command,
    CommandGrammar,
    Equip,
    Look,
    Move,
    Rejected,
    Take,
    Use,
    Wait,
)
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

FRAME_SCHEMA = "glyphwright.frame/1"
EVENT_SCHEMA = "glyphwright.event/1"
REJECTION_SCHEMA = "glyphwright.rejection/1"
QUERY_SCHEMA = "glyphwright.query/1"


def encode_frame(frame: SemanticFrame) -> dict[str, Any]:
    return {
        "schema": FRAME_SCHEMA,
        "turn": frame.turn,
        "mode": frame.mode,
        "viewport": {
            "kind": frame.viewport.kind,
            "area": frame.viewport.area,
            "origin": list(frame.viewport.origin),
            "tiles": list(frame.viewport.tiles),
            "legend": dict(frame.viewport.legend),
        },
        "actors": [
            {
                "id": actor.id,
                "name": actor.name,
                "hp": [actor.hp, actor.max_hp],
                "statuses": list(actor.statuses),
                "at": str(actor.at),
            }
            for actor in frame.actors
        ],
        "messages": list(frame.messages),
        "prompt": {"kind": frame.prompt.kind},
        "commands": encode_grammar(frame.commands),
    }


def encode_grammar(grammar: CommandGrammar) -> dict[str, Any]:
    """Encode the grammar as verb -> list of per-argument domains.

    Every verb uses the same shape, including verbs that take no arguments, so a
    consumer never special-cases arity.
    """
    return {
        "verbs": {
            verb: [list(domain) for domain in domains]
            for verb, domains in grammar.verbs
        }
    }


def encode_event(event: Event, *, turn: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": EVENT_SCHEMA,
        "turn": turn,
        "type": event.type,
    }
    match event:
        case Moved():
            payload |= {
                "actor": event.actor,
                "origin": str(event.origin),
                "destination": str(event.destination),
                "exit": event.exit,
            }
        case MoveBlocked():
            payload |= {
                "actor": event.actor,
                "origin": str(event.origin),
                "exit": event.exit,
                "reason": event.reason,
            }
        case TurnAdvanced():
            payload |= {"turn_now": event.turn}
        case ItemAcquired():
            payload |= {
                "actor": event.actor,
                "item": event.item,
                "origin": str(event.origin),
            }
        case ItemUsed():
            payload |= {
                "actor": event.actor,
                "item": event.item,
                "target": event.target,
                "consumed": event.consumed,
            }
        case ItemEquipped():
            payload |= {
                "actor": event.actor,
                "item": event.item,
                "slot": event.slot,
                "replaced": event.replaced,
            }
        case Healed():
            payload |= {
                "target": event.target,
                "amount": event.amount,
                "source": event.source,
            }
    return payload


def encode_rejection(rejection: Rejected, *, turn: int) -> dict[str, Any]:
    return {
        "schema": REJECTION_SCHEMA,
        "turn": turn,
        "command": rejection.command,
        "reason": rejection.reason,
        "hint": rejection.hint,
    }


def decode_command(text: str) -> Command | None:
    """Parse one line of the command language. ``None`` if it is not one."""
    parts = text.strip().split()
    if not parts:
        return None
    match parts:
        case ["move", token]:
            return Move(exit=token)
        case ["look"]:
            return Look()
        case ["wait"]:
            return Wait()
        case ["take", item]:
            return Take(item=item)
        case ["use", item]:
            return Use(item=item)
        case ["equip", item]:
            return Equip(item=item)
        case _:
            return None
