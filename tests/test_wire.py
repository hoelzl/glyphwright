"""The wire format is the contract, so it may not drift silently.

Schemas are generated from the encoders and committed under ``schemas/``; this
asserts the two agree, and that real output validates against them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError

from glyphwright.api import Engine, reference_pack
from glyphwright.frontends.wire import (
    EVENT_SCHEMA,
    FRAME_SCHEMA,
    decode_command,
    encode_command,
    encode_event,
    encode_frame,
    encode_rejection,
)
from glyphwright.harness.schema import REGENERATE, all_schemas, render
from glyphwright.kernel.commands import Look, Move, Wait

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"


def _validate(payload: dict[str, Any], filename: str) -> None:
    # v0 finding H10: v0's hand-rolled check looked only at top-level fields.
    Draft202012Validator(all_schemas()[filename]).validate(payload)


@pytest.mark.parametrize("filename", sorted(all_schemas()))
def test_committed_schema_matches_generated(filename: str) -> None:
    committed = (SCHEMA_DIR / filename).read_text(encoding="utf-8")
    assert committed == render(all_schemas()[filename]), (
        f"{filename} is stale; run `{REGENERATE}` and review the diff"
    )


@pytest.mark.parametrize("filename", sorted(all_schemas()))
def test_every_schema_is_a_valid_schema(filename: str) -> None:
    Draft202012Validator.check_schema(all_schemas()[filename])


def test_every_wire_schema_is_committed() -> None:
    on_disk = {path.name for path in SCHEMA_DIR.glob("*.json")}
    assert on_disk == set(all_schemas())


def test_a_real_frame_validates() -> None:
    engine = Engine.new(reference_pack(), seed=1)
    _validate(encode_frame(engine.frame()), "glyphwright.frame.v1.json")


def test_real_events_validate() -> None:
    engine = Engine.new(reference_pack(), seed=1)
    seen = set()
    for command in (Move("east"), Move("north"), Wait()):
        result = engine.step(command)
        for event in result.events:
            _validate(
                encode_event(event, turn=result.frame.turn),
                "glyphwright.event.v1.json",
            )
            seen.add(event.type)
    assert seen == {"Moved", "MoveBlocked", "TurnAdvanced"}


def test_an_event_with_another_types_field_is_invalid() -> None:
    # v0 finding H1: the flat event schema accepted any field on any event.
    engine = Engine.new(reference_pack(), seed=1)
    moved = encode_event(engine.step(Move("east")).events[0], turn=1)
    with pytest.raises(ValidationError):
        _validate(moved | {"reason": "wall"}, "glyphwright.event.v1.json")


def test_a_real_rejection_validates() -> None:
    engine = Engine.new(reference_pack(), seed=1)
    result = engine.step(Move("up"))
    assert result.rejection is not None
    _validate(
        encode_rejection(result.rejection, turn=result.frame.turn),
        "glyphwright.rejection.v1.json",
    )


def test_the_session_header_validates() -> None:
    engine = Engine.new(reference_pack(), seed=7)
    _validate(engine.fingerprint().header(harness=True), "glyphwright.session.v1.json")


def test_frames_and_events_carry_their_schema_tag() -> None:
    engine = Engine.new(reference_pack(), seed=1)
    result = engine.step(Move("east"))
    assert encode_frame(result.frame)["schema"] == FRAME_SCHEMA
    assert encode_event(result.events[0], turn=1)["schema"] == EVENT_SCHEMA


def test_encoded_frames_are_json_serialisable() -> None:
    engine = Engine.new(reference_pack(), seed=1)
    json.dumps(encode_frame(engine.frame()))


def test_encoded_grid_cells_omit_empty_tiers() -> None:
    """``ground`` is always present; ``fixture`` and ``actor`` are omitted, not
    null, when empty, so the object schema and the encoder cannot drift."""
    engine = Engine.new(reference_pack(), seed=1)
    cells = encode_frame(engine.frame())["viewport"]["cells"]
    assert cells[1][1] == {"ground": ".", "actor": "@"}
    assert cells[3][2] == {"ground": ".", "actor": "g"}
    assert cells[0][0] == {"ground": "#"}


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


@pytest.mark.parametrize("command", [Move("east"), Look(), Wait()])
def test_encoding_and_decoding_round_trip(command: object) -> None:
    assert decode_command(encode_command(command)) == command  # type: ignore[arg-type]
