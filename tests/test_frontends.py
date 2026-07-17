"""Frontends are pure functions over frames, and the plain one round-trips."""

from __future__ import annotations

import io

from hypothesis import given, settings
from hypothesis import strategies as st

from glyphwright.api import Engine
from glyphwright.content.pack import reference_pack
from glyphwright.frontends import plain
from glyphwright.kernel.commands import Command, Look, Move, Wait

commands = st.one_of(
    st.sampled_from(("north", "east", "south", "west")).map(Move),
    st.just(Look()),
    st.just(Wait()),
)


def test_render_is_a_pure_function_of_the_frame() -> None:
    frame = Engine.new(reference_pack(), seed=1).frame()
    assert plain.render(frame) == plain.render(frame)


def test_the_transcript_opens_with_the_parse_anchor() -> None:
    frame = Engine.new(reference_pack(), seed=1).frame()
    assert plain.render(frame).splitlines()[0] == "== turn 0 · exploration · village =="


@settings(max_examples=60, deadline=None)
@given(script=st.lists(commands, max_size=15))
def test_render_then_parse_recovers_the_projection(script: list[Command]) -> None:
    engine = Engine.new(reference_pack(), seed=2)
    frame = engine.frame()
    for command in script:
        frame = engine.step(command).frame
    assert plain.parse(plain.render(frame)) == plain.project(frame)


def test_a_blocked_move_is_reported_in_prose() -> None:
    engine = Engine.new(reference_pack(), seed=1)
    frame = engine.step(Move("north")).frame
    assert "A wall blocks the way north." in frame.messages


def test_the_plain_session_ends_cleanly_on_quit() -> None:
    engine = Engine.new(reference_pack(), seed=1)
    output = io.StringIO()
    code = plain.run_session(engine, io.StringIO("move east\nquit\n"), output)
    assert code == 0
    assert "session ended" in output.getvalue()


def test_the_plain_session_explains_an_unparsable_line() -> None:
    engine = Engine.new(reference_pack(), seed=1)
    output = io.StringIO()
    plain.run_session(engine, io.StringIO("dance\nquit\n"), output)
    assert "'dance'" in output.getvalue()


def test_the_plain_session_reports_a_rejection_without_advancing() -> None:
    engine = Engine.new(reference_pack(), seed=1)
    output = io.StringIO()
    plain.run_session(engine, io.StringIO("move up\nquit\n"), output)
    assert "no_such_exit" in output.getvalue()
    assert engine.frame().turn == 0
