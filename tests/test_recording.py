"""Recording and replay: a run re-executes to an exact verdict."""

from __future__ import annotations

import io
import json

import pytest
from jsonschema import Draft202012Validator

from glyphwright.api import reference_pack
from glyphwright.harness import fingerprint
from glyphwright.harness.recording import RecordingEngine, replay
from glyphwright.harness.schema import recording_schema, session_schema
from glyphwright.kernel.commands import Attack, Command, Move, Take

SCRIPT: tuple[Command, ...] = (
    Move("east"),
    Move("east"),
    Take("potion-minor"),
    Move("west"),
    Move("south"),
    Attack("goblin-1"),
)


def _record(script: tuple[Command, ...] = SCRIPT, *, seed: int = 9) -> str:
    sink = io.StringIO()
    engine = RecordingEngine.recording(reference_pack(), seed=seed, sink=sink)
    for command in script:
        engine.step(command)
    return sink.getvalue()


def _lines(text: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in text.splitlines()]


def test_a_recording_is_a_header_then_one_line_per_accepted_step() -> None:
    lines = _lines(_record((*SCRIPT[:2], Move("nowhere"), Move("north"))))
    Draft202012Validator(session_schema()).validate(lines[0])
    for line in lines[1:]:
        Draft202012Validator(recording_schema()).validate(line)
    # The rejected move is not part of the run.
    assert [line["command"] for line in lines[1:]] == [
        "move east",
        "move east",
        "move north",
    ]


def test_a_recording_replays_to_the_same_final_state() -> None:
    sink = io.StringIO()
    engine = RecordingEngine.recording(reference_pack(), seed=9, sink=sink)
    for command in SCRIPT:
        engine.step(command)
    outcome = replay(reference_pack(), io.StringIO(sink.getvalue()))
    assert (outcome.ok, outcome.steps, outcome.problem) == (True, len(SCRIPT), None)
    assert outcome.engine is not None
    assert outcome.engine._state == engine._state


def test_a_tampered_digest_names_the_step_that_diverged() -> None:
    lines = _record().splitlines()
    step = json.loads(lines[3])
    step["events"] = "sha256:" + "0" * 64
    lines[3] = json.dumps(step)
    outcome = replay(reference_pack(), lines)
    assert not outcome.ok and outcome.steps == 2
    assert outcome.problem == (
        "step 3: 'take potion-minor' produced different events than recorded"
    )


def test_another_rules_revision_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _record()
    monkeypatch.setattr("glyphwright.harness.recording.RULES", fingerprint.RULES + 1)
    outcome = replay(reference_pack(), io.StringIO(text))
    assert outcome.problem is not None
    assert outcome.problem.startswith(
        f"recorded under rules {fingerprint.RULES}, "
        f"replaying under rules {fingerprint.RULES + 1}"
    )


def test_another_pack_is_refused_by_name() -> None:
    lines = _record().splitlines()
    header = json.loads(lines[0])
    header["pack"] = "other@sha256:00"
    lines[0] = json.dumps(header)
    outcome = replay(reference_pack(), lines)
    assert outcome.problem is not None and "recorded against pack" in outcome.problem


def test_a_byte_order_mark_does_not_break_the_header() -> None:
    # v0 finding H8: a Windows editor's resave broke replay.
    outcome = replay(reference_pack(), io.StringIO("﻿" + _record()))
    assert outcome.ok


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("", "the recording is empty: no session header"),
        ("{not json\n", "the session header is not JSON"),
        ('{"schema": "glyphwright.session/1"}\n', "the first line is not a"),
    ],
)
def test_a_bad_header_is_refused_with_a_reason(text: str, problem: str) -> None:
    outcome = replay(reference_pack(), io.StringIO(text))
    assert outcome.problem is not None and outcome.problem.startswith(problem)


def test_a_misnumbered_step_is_refused() -> None:
    lines = _record().splitlines()
    step = json.loads(lines[1])
    step["step"] = 2
    lines[1] = json.dumps(step)
    outcome = replay(reference_pack(), lines)
    assert outcome.problem == "step 1: the line is numbered 2"
