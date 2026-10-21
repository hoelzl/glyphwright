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

from glyphwright.frames.frame import GridView, SemanticFrame, Viewport
from glyphwright.kernel.commands import (
    Command,
    CommandGrammar,
    Look,
    Move,
    Rejected,
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
EVENT_SCHEMA = "glyphwright.event/2"
REJECTION_SCHEMA = "glyphwright.rejection/1"
QUERY_SCHEMA = "glyphwright.query/1"


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
