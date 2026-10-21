"""Wire encoding: the actual interoperability contract.

These JSON encodings, not the dataclasses, are what an external consumer reads.
Every frame and event carries a schema tag so the contract cannot drift
silently. Widening a closed shape bumps its tag (decision 0002).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, assert_never

from glyphwright.frames.frame import GridView, MenuView, SemanticFrame, Viewport
from glyphwright.kernel.commands import (
    Attack,
    Command,
    CommandGrammar,
    Equip,
    Flee,
    Look,
    Move,
    Rejected,
    Take,
    Use,
    Wait,
)
from glyphwright.kernel.events import (
    ActorDied,
    AttackMissed,
    DamageDealt,
    Defeated,
    Event,
    FleeFailed,
    Healed,
    ItemAcquired,
    ItemEquipped,
    ItemUsed,
    ModePopped,
    ModePushed,
    MoveBlocked,
    Moved,
    Provoked,
    TurnAdvanced,
)

FRAME_SCHEMA = "glyphwright.frame/3"
EVENT_SCHEMA = "glyphwright.event/3"
REJECTION_SCHEMA = "glyphwright.rejection/1"
QUERY_SCHEMA = "glyphwright.query/2"


def _encode_viewport(viewport: Viewport) -> dict[str, Any]:
    if isinstance(viewport, GridView):
        return {
            "kind": viewport.kind,
            "area": viewport.area,
            "origin": list(viewport.origin),
            "cells": [
                [
                    {"ground": cell.ground}
                    | ({"fixture": cell.fixture} if cell.fixture is not None else {})
                    | ({"actor": cell.actor} if cell.actor is not None else {})
                    for cell in row
                ]
                for row in viewport.cells
            ],
            "legend": dict(viewport.legend),
        }
    if isinstance(viewport, MenuView):
        return {
            "kind": viewport.kind,
            "area": viewport.area,
            "combatants": list(viewport.combatants),
        }
    assert_never(viewport)


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
                "at": str(actor.at),
            }
            for actor in frame.actors
        ],
        "messages": list(frame.messages),
        "inventory": [
            {"id": item.id, "name": item.name}
            | ({"slot": item.slot} if item.slot is not None else {})
            for item in frame.inventory
        ],
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
            }
        case ItemEquipped():
            payload |= {"actor": event.actor, "item": event.item, "slot": event.slot}
            if event.replaced is not None:
                payload |= {"replaced": event.replaced}
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
                "amount": event.amount,
            }
        case AttackMissed():
            payload |= {"source": event.source, "target": event.target}
        case Provoked() | ActorDied() | Defeated() | FleeFailed():
            payload |= {"actor": event.actor}
        case ModePushed():
            payload |= {"mode": event.mode, "initiative": list(event.initiative)}
        case ModePopped():
            payload |= {"mode": event.mode, "outcome": event.outcome}
        case _:
            assert_never(event)
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
    canonical form cannot drift between the JSONL frontend and hashes.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class VerbSpec:
    """Everything the command language says about one verb.

    The decoder, the plain frontend's help, the API's rejection vocabulary,
    and the generated command reference all read this table, so a verb is
    described once.
    """

    verb: str
    build: Callable[..., Command]
    arguments: tuple[str, ...]
    summary: str
    spends_turn: bool
    events: tuple[str, ...]
    reason: str | None = None
    options_hint: str | None = None
    empty_hint: str | None = None

    def usage(self) -> str:
        """The verb with a placeholder per argument, such as ``move <exit>``."""
        return " ".join((self.verb, *(f"<{name}>" for name in self.arguments)))


VERBS: tuple[VerbSpec, ...] = (
    VerbSpec(
        "move",
        Move,
        ("exit",),
        "Walk through an exit or a portal.",
        spends_turn=True,
        events=("Moved", "MoveBlocked", "TurnAdvanced"),
        reason="no_such_exit",
        options_hint="exits here",
        empty_hint="there are no exits here",
    ),
    VerbSpec(
        "look",
        Look,
        (),
        "Look around again; the turn does not pass.",
        spends_turn=False,
        events=(),
    ),
    VerbSpec(
        "wait",
        Wait,
        (),
        "Let one turn pass.",
        spends_turn=True,
        events=("TurnAdvanced",),
    ),
    VerbSpec(
        "take",
        Take,
        ("item",),
        "Pick up an item lying where you stand.",
        spends_turn=True,
        events=("ItemAcquired", "TurnAdvanced"),
        reason="not_here",
        options_hint="you can take",
        empty_hint="there is nothing here to take",
    ),
    VerbSpec(
        "use",
        Use,
        ("item",),
        "Use a carried consumable on yourself; offered only when it would help.",
        spends_turn=True,
        events=("ItemUsed", "Healed", "TurnAdvanced"),
        reason="not_usable",
        options_hint="you can use",
        # v2 finding N11: v0 said "you are carrying nothing usable" even when
        # the player carried a potion at full hp.
        empty_hint="nothing you carry would have an effect now",
    ),
    VerbSpec(
        "equip",
        Equip,
        ("item",),
        "Wear a carried item in its slot, replacing what was there.",
        spends_turn=True,
        events=("ItemEquipped", "TurnAdvanced"),
        reason="not_equippable",
        options_hint="you can equip",
        empty_hint="you are carrying nothing to equip",
    ),
    VerbSpec(
        "attack",
        Attack,
        ("target",),
        "Strike a foe in the battle.",
        spends_turn=True,
        events=("DamageDealt", "AttackMissed", "ActorDied", "TurnAdvanced"),
        reason="no_such_target",
        options_hint="you can attack",
        empty_hint="there is no one to attack",
    ),
    VerbSpec(
        "flee",
        Flee,
        (),
        "Break away with one step; it fails when no step breaks contact.",
        spends_turn=True,
        events=("ModePopped", "Moved", "FleeFailed", "TurnAdvanced"),
    ),
)
VERB_SPECS: dict[str, VerbSpec] = {spec.verb: spec for spec in VERBS}


def encode_command(command: Command) -> str:
    """Write one command in the command language.

    The inverse of :func:`decode_command`: what this writes, that parses. The
    rejection echo depends on it, and so will recordings.
    """
    return " ".join((command.verb, *command.args()))


def decode_command(text: str) -> Command | None:
    """Parse one line of the command language. ``None`` if it is not one."""
    match text.strip().split():
        case [verb, *arguments] if verb in VERB_SPECS:
            spec = VERB_SPECS[verb]
            if len(arguments) == len(spec.arguments):
                return spec.build(*arguments)
            return None
        case _:
            return None
