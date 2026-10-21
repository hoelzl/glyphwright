"""Queries read state by stable paths, explain stats, and never pass a turn."""

from __future__ import annotations

import io
import json
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from glyphwright.api import Engine, reference_pack
from glyphwright.frontends import jsonl, plain
from glyphwright.harness.schema import query_schema
from glyphwright.kernel.commands import Equip, Move, Take


def _engine() -> Engine:
    return Engine.new(reference_pack(), seed=1)


def _armed() -> Engine:
    engine = _engine()
    for token in ("east",) * 5 + ("south",) * 2:
        engine.step(Move(token))
    engine.step(Take("iron-sword"))
    engine.step(Equip("iron-sword"))
    return engine


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("world.turn", 0),
        ("world.mode", "exploration"),
        ("player.hp", [17, 20]),
        ("player.position", "village:1,1"),
        ("player.inventory", []),
        ("player.equipment", {}),
        ("player.stats.atk", 5),
        ("potion-minor.position", "village:3,1"),
    ],
)
def test_paths_answer_what_is_true_now(path: str, value: object) -> None:
    result = _engine().query(path)
    assert (result.value, result.error) == (value, None)


def test_world_entities_lists_every_id_sorted() -> None:
    ids = _engine().query("world.entities").value
    assert isinstance(ids, list)
    assert ids == sorted(ids) and "player" in ids


@pytest.mark.parametrize(
    ("path", "error"),
    [
        ("ghost.hp", "no_such_entity"),
        ("player.colour", "no_such_path"),
        ("world", "no_such_path"),
        ("player.stats.luck", "no_such_stat"),
        ("potion-minor.stats.atk", "no_such_path"),
    ],
)
def test_unknown_paths_are_errors_as_data(path: str, error: str) -> None:
    assert _engine().query(path).error == error


def test_a_stat_query_carries_its_derivation() -> None:
    result = _armed().query("player.stats.atk")
    assert result.value == 8
    assert [(step.op, step.running) for step in result.explanation] == [
        ("base", 5),
        ("add", 8),
    ]
    assert result.explanation[1].source == "iron-sword (equipped weapon)"


def test_a_query_does_not_pass_the_turn() -> None:
    engine = _engine()
    engine.query("player.stats.atk")
    assert engine.frame().turn == 0


def _meta(engine: Engine, line: str) -> dict[str, Any]:
    output = io.StringIO()
    jsonl.run_session(engine, io.StringIO(line + "\nquit\n"), output, harness=True)
    payload: dict[str, Any] = json.loads(output.getvalue().splitlines()[-1])
    return payload


def test_explain_is_structured_on_the_wire() -> None:
    # v2 finding N9: v0's explanation was prose an agent had to parse.
    payload = _meta(_armed(), ":query player.stats.atk --explain")
    Draft202012Validator(query_schema()).validate(payload)
    assert payload["explanation"] == [
        {"source": "base", "op": "base", "value": 5, "running": 5},
        {
            "source": "iron-sword (equipped weapon)",
            "op": "add",
            "value": 3,
            "running": 8,
        },
    ]


def test_without_explain_only_the_value_is_sent() -> None:
    payload = _meta(_armed(), ":query player.stats.atk")
    assert payload == {
        "schema": payload["schema"],
        "path": "player.stats.atk",
        "value": 8,
    }


def test_a_query_error_is_valid_on_the_wire() -> None:
    payload = _meta(_engine(), ":query ghost.hp")
    Draft202012Validator(query_schema()).validate(payload)
    assert payload["error"] == "no_such_entity"


def test_the_plain_frontend_renders_the_explanation_as_text() -> None:
    output = io.StringIO()
    script = ":query player.stats.atk --explain\nquit\n"
    plain.run_session(_armed(), io.StringIO(script), output, harness=True)
    assert (
        "player.stats.atk = 8\n  base 5\n  +3 iron-sword (equipped weapon)\n"
        in output.getvalue()
    )
