"""Wire encoding: the actual interoperability contract.

With no shared Python types across the verification boundary, these JSON
encodings — not the dataclasses — are what an external adapter consumes. Every
frame and event carries a schema tag so the contract cannot drift silently
(design 0003 section 15, ADR-006).
"""

from __future__ import annotations

from typing import Any

from glyphwright.frames.frame import (
    DialogueView,
    GridView,
    LockView,
    RoomView,
    SemanticFrame,
    Viewport,
)
from glyphwright.kernel.commands import (
    Abort,
    Attack,
    Cast,
    Choose,
    Command,
    CommandGrammar,
    Equip,
    Flee,
    Look,
    Move,
    Open,
    Pick,
    Rejected,
    Take,
    Talk,
    Use,
    Wait,
)
from glyphwright.kernel.events import (
    ActorDied,
    AttackMissed,
    CastFizzled,
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
    ManaRestored,
    ManaSpent,
    MinigameResolved,
    ModePopped,
    ModePushed,
    MoveBlocked,
    Moved,
    PerkGained,
    PinSet,
    PinSlipped,
    StatusApplied,
    StatusExpired,
    TurnAdvanced,
)

# Widening a closed contract bumps the tag (ADR-006). Prior tags were retired
# rather than kept in a compatibility matrix because no external consumer
# existed before the bumps (event: items v2, combat v3, battle v4; frame: the
# menu viewport variant v2, the room viewport variant v3, the
# dialogue and lock viewport variants v4).
FRAME_SCHEMA = "glyphwright.frame/5"
EVENT_SCHEMA = "glyphwright.event/9"
REJECTION_SCHEMA = "glyphwright.rejection/1"
QUERY_SCHEMA = "glyphwright.query/1"


def _encode_viewport(viewport: Viewport) -> dict[str, Any]:
    if isinstance(viewport, GridView):
        return {
            "kind": viewport.kind,
            "area": viewport.area,
            "origin": list(viewport.origin),
            "tiles": list(viewport.tiles),
            "legend": dict(viewport.legend),
        }
    if isinstance(viewport, DialogueView):
        return {
            "kind": viewport.kind,
            "area": viewport.area,
            "speaker": viewport.speaker,
            "text": viewport.text,
            "choices": list(viewport.choices),
        }
    if isinstance(viewport, LockView):
        return {
            "kind": viewport.kind,
            "area": viewport.area,
            "target": viewport.target,
            "pins": viewport.pins,
            "total": viewport.total,
        }
    if isinstance(viewport, RoomView):
        return {
            "kind": viewport.kind,
            "area": viewport.area,
            "room": viewport.room,
            "name": viewport.name,
            "description": viewport.description,
            "contents": list(viewport.contents),
            "exits": list(viewport.exits),
        }
    return {
        "kind": viewport.kind,
        "area": viewport.area,
        "combatants": list(viewport.combatants),
    }


def encode_frame(frame: SemanticFrame) -> dict[str, Any]:
    return {
        "schema": FRAME_SCHEMA,
        "turn": frame.turn,
        "mode": frame.mode,
        "viewport": _encode_viewport(frame.viewport),
        "actors": [
            {
                "id": actor.id,
                "name": actor.name,
                "hp": [actor.hp, actor.max_hp],
                "statuses": list(actor.statuses),
                "at": str(actor.at),
            }
            | ({"mp": list(actor.mp)} if actor.mp is not None else {})
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
            if event.rng is not None:
                payload |= {"rng": event.rng}
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
        case DamageDealt():
            payload |= {
                "source": event.source,
                "target": event.target,
                "ability": event.ability,
                "damage_type": event.damage_type,
                "amount": event.amount,
            }
        case AttackMissed():
            payload |= {
                "source": event.source,
                "target": event.target,
                "ability": event.ability,
            }
        case ActorDied():
            payload |= {"actor": event.actor}
        case FlagSet():
            payload |= {"flag": event.flag, "value": event.value}
        case ModePushed():
            payload |= {"mode": event.mode, "initiative": list(event.initiative)}
            if event.returns:
                payload |= {
                    "returns": [
                        [combatant, str(origin)] for combatant, origin in event.returns
                    ]
                }
        case ModePopped():
            payload |= {"mode": event.mode, "outcome": event.outcome}
        case FleeFailed():
            payload |= {"actor": event.actor}
        case FocusSet():
            payload |= {"entity": event.entity, "detail": event.detail}
        case DialogueLine():
            payload |= {"speaker": event.speaker, "text": event.text}
        case ChoiceOffered():
            payload |= {"speaker": event.speaker, "choices": list(event.choices)}
        case PinSet():
            payload |= {"target": event.target, "pins": event.pins}
        case PinSlipped():
            payload |= {"target": event.target}
        case MinigameResolved():
            payload |= {
                "minigame": event.minigame,
                "outcome": event.outcome,
                "target": event.target,
            }
        case StatusApplied():
            payload |= {
                "target": event.target,
                "status": event.status,
                "expires": event.expires,
            }
        case StatusExpired():
            payload |= {"target": event.target, "status": event.status}
        case PerkGained():
            payload |= {"target": event.target, "perk": event.perk}
        case ManaSpent():
            payload |= {"caster": event.caster, "amount": event.amount}
        case ManaRestored():
            payload |= {
                "target": event.target,
                "amount": event.amount,
                "source": event.source,
            }
        case CastFizzled():
            payload |= {
                "caster": event.caster,
                "ability": event.ability,
                "target": event.target,
                "reason": event.reason,
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


def canonical_json(payload: object) -> str:
    """The one canonical JSON spelling: sorted keys, compact separators.

    Every emitted line and every digest input goes through here, so the
    canonical form cannot drift between the JSONL frontend, recordings, and
    hashes.
    """
    import json

    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def encode_command(command: Command) -> str:
    """Write one command in the command language (0003 §6).

    The inverse of :func:`decode_command`: what this writes, that parses —
    the rejection echo and the recording format both depend on it.
    """
    if isinstance(command, Cast):
        # Cast's surface syntax carries an 'at'.
        return f"cast {command.ability} at {command.target}"
    return " ".join((command.verb, *command.args()))


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
        case ["attack", target]:
            return Attack(target=target)
        case ["flee"]:
            return Flee()
        case ["talk", target]:
            return Talk(target=target)
        case ["open", target]:
            return Open(target=target)
        case ["choose", number]:
            return Choose(choice=number)
        case ["pick"]:
            return Pick()
        case ["abort"]:
            return Abort()
        case ["cast", ability, "at", target]:
            return Cast(ability=ability, target=target)
        case _:
            return None
