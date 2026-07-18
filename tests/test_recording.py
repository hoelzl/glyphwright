"""Session recording and replay: the durable run format (design 0008,
resolving 0003 §20.2). Replay does not trust determinism — it verifies it."""

from __future__ import annotations

import io
import json

import pytest

from glyphwright.api import Engine
from glyphwright.content.pack import reference_pack
from glyphwright.frontends.wire import decode_command, encode_command
from glyphwright.harness.recording import RecordingEngine, replay
from glyphwright.kernel.commands import (
    Abort,
    Attack,
    Cast,
    Choose,
    Command,
    Equip,
    Flee,
    Look,
    Move,
    Open,
    Pick,
    Take,
    Talk,
    Use,
    Wait,
)

_EVERY_COMMAND: tuple[Command, ...] = (
    Move("east"),
    Look(),
    Wait(),
    Take("dagger"),
    Use("potion"),
    Equip("dagger"),
    Attack("goblin-1"),
    Flee(),
    Talk("elder"),
    Open("strongbox"),
    Choose("2"),
    Pick(),
    Abort(),
    Cast("firebolt", "goblin-1"),
)


@pytest.mark.parametrize("command", _EVERY_COMMAND, ids=lambda c: c.verb)
def test_the_command_language_round_trips(command: Command) -> None:
    assert decode_command(encode_command(command)) == command


_SCRIPT: tuple[Command, ...] = (
    Move("east"),
    Move("east"),
    Wait(),
    Move("south"),
    Look(),  # accepted, turn-free: recorded like any accepted command
    Move("east"),
)


def _record(seed: int) -> tuple[str, Engine]:
    sink = io.StringIO()
    engine = RecordingEngine.recording(reference_pack(), seed=seed, sink=sink)
    for command in _SCRIPT:
        engine.step(command)
    engine.step(Move("up"))  # rejected: must not be recorded
    return sink.getvalue(), engine


def test_a_recording_replays_to_the_exact_final_state() -> None:
    text, recorded = _record(seed=99)
    outcome = replay(reference_pack(), text.splitlines())
    assert outcome.ok, outcome.problem
    assert outcome.engine is not None
    assert outcome.engine._state == recorded._state, (
        "restore is replay: byte-exact state, RNG cursor included"
    )


def test_only_accepted_steps_are_recorded() -> None:
    text, _ = _record(seed=99)
    lines = [json.loads(line) for line in text.splitlines()]
    header, steps = lines[0], lines[1:]
    assert header["schema"] == "glyphwright.session/1"
    assert [line["step"] for line in steps] == list(range(1, len(steps) + 1))
    commands = [line["command"] for line in steps]
    assert "look" in commands, "accepted observations are part of the run"
    assert "move up" not in commands, "rejected, not part of the run"
    assert len(steps) == len(_SCRIPT)


def test_recorded_lines_validate_against_the_committed_schema() -> None:
    from glyphwright.harness.schema import all_schemas

    schema = all_schemas()["glyphwright.recording.v1.json"]
    text, _ = _record(seed=7)
    for raw in text.splitlines()[1:]:
        line = json.loads(raw)
        assert set(line) == set(schema["properties"])
        assert line["schema"] == schema["properties"]["schema"]["const"]


def test_a_tampered_command_is_a_reported_divergence() -> None:
    text, _ = _record(seed=99)
    lines = text.splitlines()
    doctored = json.loads(lines[2])
    doctored["command"] = "wait"
    lines[2] = json.dumps(doctored)
    outcome = replay(reference_pack(), lines)
    assert not outcome.ok
    assert outcome.problem is not None and "step 2" in outcome.problem
    assert outcome.engine is None


def test_a_foreign_pack_is_refused_at_the_header() -> None:
    text, _ = _record(seed=99)
    lines = text.splitlines()
    header = json.loads(lines[0])
    header["pack"] = "someone-else@sha256:0000"
    lines[0] = json.dumps(header)
    outcome = replay(reference_pack(), lines)
    assert not outcome.ok and outcome.steps == 0
    assert outcome.problem is not None and "pack" in outcome.problem


def test_a_foreign_engine_version_is_refused_at_the_header() -> None:
    text, _ = _record(seed=99)
    lines = text.splitlines()
    header = json.loads(lines[0])
    header["engine"] = "glyphwright 0.0.0-elsewhere"
    lines[0] = json.dumps(header)
    outcome = replay(reference_pack(), lines)
    assert not outcome.ok
    assert outcome.problem is not None and "migrate" in outcome.problem


def test_an_empty_recording_is_a_diagnosis_not_a_crash() -> None:
    outcome = replay(reference_pack(), [])
    assert not outcome.ok
    assert outcome.problem is not None and "header" in outcome.problem


def test_a_misnumbered_step_is_refused() -> None:
    text, _ = _record(seed=99)
    lines = text.splitlines()
    doctored = json.loads(lines[3])
    doctored["step"] = 99
    lines[3] = json.dumps(doctored)
    outcome = replay(reference_pack(), lines)
    assert not outcome.ok
    assert outcome.problem is not None and "numbered" in outcome.problem


def test_a_recording_survives_battles_and_their_rng() -> None:
    """The digest is the §20.2 prefix hash: a battle's rolls and AI turns
    replay byte-exactly or the divergence is named."""
    sink = io.StringIO()
    engine = RecordingEngine.recording(reference_pack(), seed=67, sink=sink)
    for command in (
        Move("east"),
        Move("east"),
        Move("east"),
        Move("east"),
        Move("east"),
        Move("east"),
        Move("south"),
        Move("south"),
        Move("down"),
        Move("east"),  # the marauder engages: initiative, arena placement
        Cast("firebolt", "marauder-1"),
        Flee(),
    ):
        engine.step(command)
    outcome = replay(reference_pack(), sink.getvalue().splitlines())
    assert outcome.ok, outcome.problem
    assert outcome.engine is not None
    assert outcome.engine._state == engine._state
