"""End-to-end proof of the shipped interface, across a process boundary.

These drive the CLI in a subprocess exactly as an agent or a person would, so
they cover the wiring that in-process tests cannot: argument parsing and the
UTF-8 stdio setup.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from glyphwright.frontends.wire import EVENT_SCHEMA, FRAME_SCHEMA
from glyphwright.harness.fingerprint import SESSION_SCHEMA

pytestmark = pytest.mark.e2e

_SCRIPT = [sys.executable, "-m", "glyphwright.cli"]


def _run(argv: list[str], stdin: bytes) -> subprocess.CompletedProcess[bytes]:
    # Bytes, not text: the test sees exactly what a consumer of the pipe sees.
    return subprocess.run(
        _SCRIPT + argv, input=stdin, capture_output=True, timeout=60, check=False
    )


def _lines(result: subprocess.CompletedProcess[bytes]) -> list[dict[str, object]]:
    return [json.loads(line) for line in result.stdout.decode("utf-8").splitlines()]


def test_the_plain_frontend_plays_a_scripted_session() -> None:
    result = _run([], b"move east\nmove south\nquit\n")
    assert result.returncode == 0
    out = result.stdout.decode("utf-8")
    assert "== turn 1 | exploration | village ==" in out
    # The second step lands next to the goblin, which starts a battle.
    assert "== turn 2 | battle | village ==" in out
    assert "Battle is joined!" in out
    assert "session ended" in out


def test_output_uses_unix_newlines_on_every_platform() -> None:
    assert b"\r\n" not in _run([], b"move east\nquit\n").stdout


def test_the_plain_frontend_is_deterministic_across_processes() -> None:
    script = b"move east\nmove east\nmove south\nquit\n"
    assert _run([], script).stdout == _run([], script).stdout


def test_the_jsonl_frontend_opens_with_a_session_header() -> None:
    header = _lines(_run(["--frontend", "jsonl", "--harness"], b"quit\n"))[0]
    assert header["schema"] == SESSION_SCHEMA
    assert header["harness"] is True
    assert header["seed"] == 424242
    assert str(header["pack"]).startswith("reference-vale@sha256:")


def test_the_jsonl_frontend_emits_events_then_a_frame() -> None:
    schemas = [
        line["schema"]
        for line in _lines(_run(["--frontend", "jsonl"], b"move east\nquit\n"))
    ]
    assert schemas[0] == SESSION_SCHEMA
    assert EVENT_SCHEMA in schemas
    assert schemas[-1] == FRAME_SCHEMA


def test_invalid_utf8_on_stdin_is_escaped_not_echoed() -> None:
    # v0 finding H6, across the real pipe.
    result = _run(["--frontend", "jsonl"], b"move \xff\nquit\n")
    assert result.returncode == 0
    assert _lines(result)[-1]["command"] == "move \\xff"


def test_the_seed_is_explicit_and_recorded() -> None:
    assert (
        _lines(_run(["--frontend", "jsonl", "--seed", "7"], b"quit\n"))[0]["seed"] == 7
    )


def test_the_same_seed_and_commands_reproduce_across_processes() -> None:
    argv = ["--frontend", "jsonl", "--seed", "11"]
    script = b"move east\nmove south\nwait\nquit\n"
    assert _run(argv, script).stdout == _run(argv, script).stdout


def test_help_is_available_without_playing() -> None:
    result = _run(["--help"], b"")
    assert result.returncode == 0
    assert b"--frontend" in result.stdout


def _closet(root: Path, *, hp: int = 5) -> Path:
    (root / "pack.toml").write_text('name = "closet"\n', encoding="utf-8")
    (root / "areas.toml").write_text(
        '[[grid]]\narea = "closet"\nrows = """\n...\n"""\n', encoding="utf-8"
    )
    (root / "entities.toml").write_text(
        '[[entity]]\nid = "player"\nposition = "closet:0,0"\n\n'
        f"[entity.actor]\nname = 'Mote'\nhp = {hp}\nmax_hp = 5\n",
        encoding="utf-8",
    )
    return root


def test_an_external_pack_plays_over_the_cli(tmp_path: Path) -> None:
    result = _run(["--pack", str(_closet(tmp_path))], b"move east\nquit\n")
    assert result.returncode == 0
    assert b"== turn 1 | exploration | closet ==" in result.stdout


def test_a_broken_pack_fails_with_a_located_diagnostic(tmp_path: Path) -> None:
    result = _run(["--pack", str(_closet(tmp_path, hp=9))], b"")
    assert result.returncode == 2
    assert result.stdout == b""
    message = result.stderr.decode("utf-8").strip()
    assert message == (
        "glyphwright: entities.toml:1: entity 'player': hp 9 is outside 0..5"
    )


def test_a_recorded_session_replays_from_the_command_line(tmp_path: Path) -> None:
    recording = tmp_path / "run.jsonl"
    played = _run(["--record", str(recording)], b"move east\nmove south\nquit\n")
    assert played.returncode == 0
    # Rejected commands are not recorded, so the count says what was.
    assert played.stderr.startswith(b"recorded 2 steps to ")
    verified = _run(["--replay", str(recording)], b"")
    assert verified.returncode == 0
    assert verified.stdout == b"recording verified: 2 steps, turn 2\n"


def test_a_recording_is_never_overwritten(tmp_path: Path) -> None:
    recording = tmp_path / "run.jsonl"
    recording.write_text("keep me", encoding="utf-8")
    result = _run(["--record", str(recording)], b"quit\n")
    assert result.returncode == 2
    assert recording.read_text(encoding="utf-8") == "keep me"


def test_a_diverging_replay_exits_1_with_the_reason(tmp_path: Path) -> None:
    recording = tmp_path / "run.jsonl"
    _run(["--record", str(recording)], b"move east\nquit\n")
    lines = recording.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace("move east", "move north")
    recording.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = _run(["--replay", str(recording)], b"")
    assert result.returncode == 1
    assert result.stdout.decode("utf-8") == (
        "recording diverged after 0 steps: "
        "step 1: 'move north' produced different events than recorded\n"
    )


@pytest.mark.parametrize("extra", [["--seed", "3"], ["--record", "other.jsonl"]])
def test_replay_refuses_options_it_cannot_honour(
    tmp_path: Path, extra: list[str]
) -> None:
    result = _run(["--replay", str(tmp_path / "run.jsonl"), *extra], b"")
    assert result.returncode == 2
