"""The oracle interface: stable paths over world state, never advancing the
turn, with derivations that make "why is attack 8?" assertable (design 0003
sections 9.1, 13, 14)."""

from __future__ import annotations

import io
import json

from glyphwright.api import Engine
from glyphwright.content.pack import reference_pack
from glyphwright.frontends import jsonl, plain
from glyphwright.kernel.commands import Equip, Move, Take


def _engine() -> Engine:
    return Engine.new(reference_pack(), seed=1)


def _armed_engine() -> Engine:
    engine = _engine()
    for token in ("east", "east", "east", "east", "east", "south", "south"):
        engine.step(Move(token))
    engine.step(Take("iron-sword"))
    engine.step(Equip("iron-sword"))
    return engine


# -- Engine.query -------------------------------------------------------------


def test_query_reads_hp_without_advancing_the_turn() -> None:
    engine = _engine()
    result = engine.query("player.hp")
    assert result.value == [17, 20]
    assert result.error is None
    assert engine.frame().turn == 0


def test_query_reads_world_facts() -> None:
    engine = _engine()
    assert engine.query("world.turn").value == 0
    assert engine.query("world.mode").value == "exploration"


def test_query_reads_the_inventory_and_equipment() -> None:
    engine = _armed_engine()
    assert engine.query("player.inventory").value == ["iron-sword"]
    assert engine.query("player.equipment").value == {"weapon": "iron-sword"}


def test_query_resolves_a_stat_through_the_pipeline() -> None:
    engine = _armed_engine()
    result = engine.query("player.stats.atk")
    assert result.value == 8


def test_a_stat_query_carries_its_derivation() -> None:
    engine = _armed_engine()
    explanation = engine.query("player.stats.atk").explanation
    assert explanation, "a stat query must expose its derivation"
    text = "\n".join(explanation)
    assert "base 5" in text
    assert "iron-sword" in text


def test_an_unknown_path_is_an_error_value_not_an_exception() -> None:
    engine = _engine()
    result = engine.query("player.socks")
    assert result.error is not None
    assert result.value is None


def test_an_unknown_entity_is_an_error_value() -> None:
    engine = _engine()
    assert engine.query("balrog.hp").error is not None


def test_a_misspelled_stat_is_an_error_not_a_fabricated_zero() -> None:
    engine = _armed_engine()
    result = engine.query("player.stats.attack")
    assert result.error == "no_such_stat"
    assert result.value is None


def test_stats_of_a_non_actor_are_an_error() -> None:
    engine = _engine()
    assert engine.query("potion-minor.stats.atk").error is not None


# -- the meta-channel in the plain frontend -----------------------------------


def _plain_session(script: str, *, harness: bool = True) -> str:
    output = io.StringIO()
    plain.run_session(_engine(), io.StringIO(script), output, harness=harness)
    return output.getvalue()


def test_the_plain_meta_channel_answers_a_query() -> None:
    output = _plain_session(":query player.hp\nquit\n")
    assert "player.hp = [17, 20]" in output


def test_the_plain_meta_channel_explains_a_stat() -> None:
    output = _plain_session(":query player.stats.atk --explain\nquit\n")
    assert "base 5" in output


def test_the_meta_channel_is_gated_by_the_harness_flag() -> None:
    output = _plain_session(":query player.hp\nquit\n", harness=False)
    assert "--harness" in output
    assert "[17, 20]" not in output


def test_the_plain_meta_channel_reports_the_seed() -> None:
    output = _plain_session(":seed\nquit\n")
    assert "seed = 1" in output


def test_a_meta_query_does_not_advance_the_turn() -> None:
    engine = _engine()
    plain.run_session(
        engine, io.StringIO(":query player.hp\nquit\n"), io.StringIO(), harness=True
    )
    assert engine.frame().turn == 0


# -- the meta-channel in the JSONL frontend -----------------------------------


def _jsonl_session(script: str, *, harness: bool = True) -> list[dict[str, object]]:
    output = io.StringIO()
    jsonl.run_session(_engine(), io.StringIO(script), output, harness=harness)
    return [json.loads(line) for line in output.getvalue().splitlines()]


def test_the_jsonl_meta_channel_emits_a_tagged_query_result() -> None:
    lines = _jsonl_session(":query player.hp\nquit\n")
    results = [line for line in lines if line["schema"] == "glyphwright.query/1"]
    assert results and results[0]["path"] == "player.hp"
    assert results[0]["value"] == [17, 20]


def test_the_jsonl_meta_channel_reports_errors_as_data() -> None:
    lines = _jsonl_session(":query player.socks\nquit\n")
    results = [line for line in lines if line["schema"] == "glyphwright.query/1"]
    assert results and results[0]["error"]


def test_the_jsonl_frame_meta_command_emits_a_frame() -> None:
    lines = _jsonl_session(":frame\nquit\n")
    frames = [line for line in lines if line["schema"] == "glyphwright.frame/1"]
    # One frame on session open, one from the meta command.
    assert len(frames) == 2
