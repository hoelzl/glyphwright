"""JSON Schema generation for the wire types.

Schemas are generated from the encoders' shape and committed under ``schemas/``.
A golden test asserts the generated schemas match the committed files, so the
contract cannot drift silently; schema changes are deliberate, reviewed, and
versioned by bumping the tag (design 0003 section 15, ADR-006).

Generation is hand-rolled deliberately: the wire types are ours and stay simple,
and the engine carries no dependencies.
"""

from __future__ import annotations

import json
from typing import Any

from glyphwright.frontends.wire import (
    EVENT_SCHEMA,
    FRAME_SCHEMA,
    QUERY_SCHEMA,
    REJECTION_SCHEMA,
)
from glyphwright.harness.fingerprint import SESSION_SCHEMA

_STRING: dict[str, Any] = {"type": "string"}
_INTEGER: dict[str, Any] = {"type": "integer"}


def _object(
    properties: dict[str, Any], *, required: list[str] | None = None
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": sorted(required if required is not None else properties),
        "additionalProperties": False,
    }


def _array(items: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": items}


def session_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SESSION_SCHEMA,
        "title": "GlyphWright session header",
        **_object(
            {
                "schema": {"const": SESSION_SCHEMA},
                "engine": _STRING,
                "pack": _STRING,
                "seed": _INTEGER,
                "harness": {"type": "boolean"},
            }
        ),
    }


def frame_schema() -> dict[str, Any]:
    grid_viewport = _object(
        {
            "kind": {"const": "grid"},
            "area": _STRING,
            "origin": {
                "type": "array",
                "items": _INTEGER,
                "minItems": 2,
                "maxItems": 2,
            },
            "tiles": _array(_STRING),
            "legend": {"type": "object", "additionalProperties": _STRING},
        }
    )
    room_viewport = _object(
        {
            "kind": {"const": "room"},
            "area": _STRING,
            "room": _STRING,
            "name": _STRING,
            "description": _STRING,
            "contents": _array(_STRING),
            "exits": _array(_STRING),
        }
    )
    menu_viewport = _object(
        {
            "kind": {"const": "menu"},
            "area": _STRING,
            "combatants": _array(_STRING),
        }
    )
    viewport = {"oneOf": [grid_viewport, room_viewport, menu_viewport]}
    actor = _object(
        {
            "id": _STRING,
            "name": _STRING,
            "hp": {"type": "array", "items": _INTEGER, "minItems": 2, "maxItems": 2},
            "statuses": _array(_STRING),
            "at": _STRING,
        }
    )
    commands = _object(
        {
            "verbs": {
                "type": "object",
                "additionalProperties": _array(_array(_STRING)),
            }
        }
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": FRAME_SCHEMA,
        "title": "GlyphWright semantic frame",
        **_object(
            {
                "schema": {"const": FRAME_SCHEMA},
                "turn": _INTEGER,
                "mode": _STRING,
                "viewport": viewport,
                "actors": _array(actor),
                "messages": _array(_STRING),
                "prompt": _object({"kind": _STRING}),
                "commands": commands,
            }
        ),
    }


def event_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": EVENT_SCHEMA,
        "title": "GlyphWright event",
        "type": "object",
        "required": ["schema", "turn", "type"],
        "properties": {
            "schema": {"const": EVENT_SCHEMA},
            "turn": _INTEGER,
            "type": {
                "enum": [
                    "Moved",
                    "MoveBlocked",
                    "TurnAdvanced",
                    "ItemAcquired",
                    "ItemUsed",
                    "ItemEquipped",
                    "Healed",
                    "DamageDealt",
                    "AttackMissed",
                    "ActorDied",
                    "FlagSet",
                    "ModePushed",
                    "ModePopped",
                    "FleeFailed",
                ]
            },
            "actor": _STRING,
            "origin": _STRING,
            "destination": _STRING,
            "exit": _STRING,
            "reason": _STRING,
            "turn_now": _INTEGER,
            "item": _STRING,
            "target": _STRING,
            "consumed": {"type": "boolean"},
            "slot": _STRING,
            "replaced": {"type": ["string", "null"]},
            "amount": _INTEGER,
            "source": _STRING,
            "ability": _STRING,
            "damage_type": _STRING,
            "flag": _STRING,
            "value": {"type": "boolean"},
            "rng": _STRING,
            "mode": _STRING,
            "initiative": _array(_STRING),
            "outcome": _STRING,
        },
        "additionalProperties": False,
    }


def rejection_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": REJECTION_SCHEMA,
        "title": "GlyphWright rejection",
        **_object(
            {
                "schema": {"const": REJECTION_SCHEMA},
                "turn": _INTEGER,
                "command": _STRING,
                "reason": _STRING,
                "hint": _STRING,
            }
        ),
    }


def query_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": QUERY_SCHEMA,
        "title": "GlyphWright query result",
        "type": "object",
        "required": ["schema", "path"],
        "properties": {
            "schema": {"const": QUERY_SCHEMA},
            "path": _STRING,
            "value": {},
            "explanation": _array(_STRING),
            "error": _STRING,
        },
        "additionalProperties": False,
    }


def all_schemas() -> dict[str, dict[str, Any]]:
    """Every wire schema, keyed by the filename it is committed under."""
    return {
        "glyphwright.session.v1.json": session_schema(),
        "glyphwright.frame.v3.json": frame_schema(),
        "glyphwright.event.v4.json": event_schema(),
        "glyphwright.rejection.v1.json": rejection_schema(),
        "glyphwright.query.v1.json": query_schema(),
    }


def render(schema: dict[str, Any]) -> str:
    """Canonical on-disk form, so the golden diff is stable."""
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"
