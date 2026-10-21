"""Frontends are pure functions over frames; plain round-trips, JSONL is data."""

from __future__ import annotations

import io
import json
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from glyphwright.api import Engine, reference_pack
from glyphwright.frontends import jsonl, plain
from glyphwright.frontends.wire import EVENT_SCHEMA, FRAME_SCHEMA, QUERY_SCHEMA
from glyphwright.harness.fingerprint import SESSION_SCHEMA
from glyphwright.kernel.commands import Command, Look, Move, Wait

commands = st.one_of(
    st.sampled_from(("north", "east", "south", "west")).map(Move),
    st.just(Look()),
    st.just(Wait()),
)


def _engine() -> Engine:
    return Engine.new(reference_pack(), seed=1)


def _jsonl(stdin: str, *, harness: bool = False) -> list[dict[str, Any]]:
    output = io.StringIO()
    jsonl.run_session(_engine(), io.StringIO(stdin), output, harness=harness)
    return [json.loads(line) for line in output.getvalue().splitlines()]


def test_render_is_a_pure_function_of_the_frame() -> None:
    frame = _engine().frame()
    assert plain.render(frame) == plain.render(frame)


def test_the_transcript_opens_with_the_parse_anchor() -> None:
    first = plain.render(_engine().frame()).splitlines()[0]
    assert first == "== turn 0 | exploration | village =="


def test_the_engines_own_transcript_text_is_ascii() -> None:
    engine = _engine()
    text = plain.render(engine.step(Move("north")).frame)
    assert text.isascii()


@settings(max_examples=60, deadline=None)
@given(script=st.lists(commands, max_size=15))
def test_render_then_parse_recovers_the_projection(script: list[Command]) -> None:
    engine = Engine.new(reference_pack(), seed=2)
    frame = engine.frame()
    for command in script:
        frame = engine.step(command).frame
    assert plain.parse(plain.render(frame)) == plain.project(frame)


def test_the_plain_session_ends_cleanly_on_quit() -> None:
    output = io.StringIO()
    code = plain.run_session(_engine(), io.StringIO("move east\nquit\n"), output)
    assert code == 0
    assert "session ended" in output.getvalue()


def test_the_plain_session_explains_an_unparsable_line() -> None:
    output = io.StringIO()
    plain.run_session(_engine(), io.StringIO("dance\nquit\n"), output)
    assert "? 'dance': commands: move <exit> | look | wait | quit" in output.getvalue()


def test_the_plain_session_reports_a_rejection_without_advancing() -> None:
    engine = _engine()
    output = io.StringIO()
    plain.run_session(engine, io.StringIO("move up\nquit\n"), output)
    assert "no_such_exit" in output.getvalue()
    assert engine.frame().turn == 0


def test_jsonl_opens_with_a_header_and_a_frame() -> None:
    lines = _jsonl("quit\n")
    assert [line["schema"] for line in lines] == [
        SESSION_SCHEMA,
        FRAME_SCHEMA,
    ]


def test_jsonl_emits_events_then_a_frame() -> None:
    schemas = [line["schema"] for line in _jsonl("move east\nquit\n")]
    assert schemas[2:] == [
        EVENT_SCHEMA,
        EVENT_SCHEMA,
        FRAME_SCHEMA,
    ]


def test_jsonl_hints_come_from_the_current_grammar() -> None:
    # v0 finding H7: the hint was a hard-coded list.
    rejection = _jsonl("dance\nquit\n")[-1]
    assert rejection["reason"] == "unparsable"
    assert rejection["hint"] == "expected one of: move, look, wait, quit"


def test_jsonl_escapes_undecodable_input_in_its_echo() -> None:
    # v0 finding H6: invalid UTF-8 was echoed straight back. The CLI reads
    # stdin with surrogateescape, so a stray byte arrives as a lone surrogate.
    stray = b"move \xff".decode("utf-8", "surrogateescape")
    output = io.StringIO()
    jsonl.run_session(_engine(), io.StringIO(stray + "\nquit\n"), output)
    echoed = json.loads(output.getvalue().splitlines()[-1])["command"]
    assert echoed == "move \\xff"
    output.getvalue().encode("utf-8")  # the whole stream is valid UTF-8


def test_jsonl_meta_commands_need_the_harness_flag() -> None:
    assert _jsonl(":seed\nquit\n")[-1]["reason"] == "harness_disabled"


def test_jsonl_meta_seed_answers_with_the_run_seed() -> None:
    answer = _jsonl(":seed\nquit\n", harness=True)[-1]
    assert answer == {"schema": QUERY_SCHEMA, "path": "seed", "value": 1}


def test_jsonl_meta_frame_does_not_advance_the_turn() -> None:
    lines = _jsonl("move east\n:frame\nquit\n", harness=True)
    assert lines[-1]["schema"] == FRAME_SCHEMA
    assert lines[-1]["turn"] == 1


def test_an_unknown_meta_command_is_rejected_as_data() -> None:
    answer = _jsonl(":dance\nquit\n", harness=True)[-1]
    assert (answer["reason"], answer["hint"]) == (
        "unknown_meta",
        ":seed | :frame [--json]",
    )
