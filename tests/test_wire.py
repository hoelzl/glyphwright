"""The wire format is the contract, so it may not drift silently.

Schemas are generated from the encoders and committed under ``schemas/``; this
asserts the two agree, and that real output validates against them (design 0003
section 15, ADR-006).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from glyphwright.api import Engine
from glyphwright.content.pack import reference_pack
from glyphwright.frontends.wire import (
    EVENT_SCHEMA,
    FRAME_SCHEMA,
    decode_command,
    encode_event,
    encode_frame,
    encode_rejection,
)
from glyphwright.harness.schema import all_schemas, render
from glyphwright.kernel.commands import Look, Move, Wait

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"


@pytest.mark.parametrize("filename", sorted(all_schemas()))
def test_committed_schema_matches_generated(filename: str) -> None:
    committed = (SCHEMA_DIR / filename).read_text(encoding="utf-8")
    assert committed == render(all_schemas()[filename]), (
        f"{filename} is stale; regenerate it and review the diff deliberately"
    )


def test_every_wire_schema_is_committed() -> None:
    on_disk = {path.name for path in SCHEMA_DIR.glob("*.json")}
    assert on_disk == set(all_schemas())


def _check(payload: dict[str, Any], schema: dict[str, Any]) -> None:
    """A deliberately small structural validator.

    Enough to catch an encoder emitting an undeclared or missing field, without
    taking a jsonschema dependency for four flat object types.
    """
    for key in schema["required"]:
        assert key in payload, f"missing required field: {key}"
    if not schema.get("additionalProperties", True):
        undeclared = set(payload) - set(schema["properties"])
        assert not undeclared, f"undeclared fields: {sorted(undeclared)}"
    for key, value in payload.items():
        spec = schema["properties"][key]
        if "const" in spec:
            assert value == spec["const"]
        elif "enum" in spec:
            assert value in spec["enum"]
        elif spec.get("type") == "integer":
            assert isinstance(value, int)
        elif spec.get("type") == "string":
            assert isinstance(value, str)
        elif spec.get("type") == "array":
            assert isinstance(value, list)
        elif spec.get("type") == "object":
            assert isinstance(value, dict)


def test_a_real_frame_validates() -> None:
    engine = Engine.new(reference_pack(), seed=1)
    _check(encode_frame(engine.frame()), all_schemas()["glyphwright.frame.v5.json"])


def test_real_events_validate() -> None:
    engine = Engine.new(reference_pack(), seed=1)
    schema = all_schemas()["glyphwright.event.v9.json"]
    for command in (Move("east"), Move("north"), Wait()):
        result = engine.step(command)
        for event in result.events:
            _check(encode_event(event, turn=result.frame.turn), schema)


def test_a_real_rejection_validates() -> None:
    engine = Engine.new(reference_pack(), seed=1)
    result = engine.step(Move("up"))
    assert result.rejection is not None
    _check(
        encode_rejection(result.rejection, turn=result.frame.turn),
        all_schemas()["glyphwright.rejection.v1.json"],
    )


def test_the_session_header_validates() -> None:
    engine = Engine.new(reference_pack(), seed=7)
    _check(
        engine.fingerprint().header(harness=True),
        all_schemas()["glyphwright.session.v1.json"],
    )


def test_frames_and_events_carry_their_schema_tag() -> None:
    engine = Engine.new(reference_pack(), seed=1)
    result = engine.step(Move("east"))
    assert encode_frame(result.frame)["schema"] == FRAME_SCHEMA
    assert encode_event(result.events[0], turn=1)["schema"] == EVENT_SCHEMA


def test_encoded_frames_are_json_serialisable() -> None:
    engine = Engine.new(reference_pack(), seed=1)
    json.dumps(encode_frame(engine.frame()))


def test_the_grammar_uses_one_shape_for_every_arity() -> None:
    engine = Engine.new(reference_pack(), seed=1)
    verbs = encode_frame(engine.frame())["commands"]["verbs"]
    assert verbs["look"] == []
    assert verbs["move"] and isinstance(verbs["move"][0], list)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("move east", Move("east")),
        ("  move   east  ", Move("east")),
        ("look", Look()),
        ("wait", Wait()),
    ],
)
def test_commands_decode(text: str, expected: object) -> None:
    assert decode_command(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "dance", "move", "move east west"])
def test_non_commands_decode_to_none(text: str) -> None:
    assert decode_command(text) is None
