"""End-to-end proof of the shipped interface, across a process boundary.

These drive the installed console script exactly as an agent or a person would,
so they cover the wiring that in-process tests cannot (design 0003 section 16.3).
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

pytestmark = pytest.mark.e2e

_SCRIPT = [sys.executable, "-m", "glyphwright.cli"]


def _run(argv: list[str], stdin: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _SCRIPT + argv,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_the_plain_frontend_plays_a_scripted_session() -> None:
    result = _run([], "move east\nmove south\nquit\n")
    assert result.returncode == 0
    assert "== turn 1 · exploration · village ==" in result.stdout
    assert "== turn 2 · exploration · village ==" in result.stdout
    assert "session ended" in result.stdout


def test_the_plain_frontend_is_deterministic_across_processes() -> None:
    script = "move east\nmove east\nmove south\nquit\n"
    assert _run([], script).stdout == _run([], script).stdout


def test_the_jsonl_frontend_opens_with_a_session_header() -> None:
    result = _run(["--frontend", "jsonl", "--harness"], "quit\n")
    header = json.loads(result.stdout.splitlines()[0])
    assert header["schema"] == "glyphwright.session/1"
    assert header["harness"] is True
    assert header["seed"] == 424242
    assert header["pack"].startswith("reference-vale@sha256:")


def test_the_jsonl_frontend_emits_events_then_a_frame() -> None:
    result = _run(["--frontend", "jsonl"], "move east\nquit\n")
    lines = [json.loads(line) for line in result.stdout.splitlines()]
    schemas = [line["schema"] for line in lines]
    assert schemas[0] == "glyphwright.session/1"
    assert "glyphwright.event/8" in schemas
    assert schemas[-1] == "glyphwright.frame/4"


def test_the_jsonl_frontend_rejects_an_unparsable_line_as_data() -> None:
    result = _run(["--frontend", "jsonl"], "dance\nquit\n")
    lines = [json.loads(line) for line in result.stdout.splitlines()]
    rejections = [line for line in lines if line["schema"] == "glyphwright.rejection/1"]
    assert rejections and rejections[0]["reason"] == "unparsable"


def test_the_seed_is_explicit_and_recorded() -> None:
    result = _run(["--frontend", "jsonl", "--seed", "7"], "quit\n")
    assert json.loads(result.stdout.splitlines()[0])["seed"] == 7


def test_the_same_seed_and_commands_reproduce_across_processes() -> None:
    argv = ["--frontend", "jsonl", "--seed", "11"]
    script = "move east\nmove south\nwait\nquit\n"
    assert _run(argv, script).stdout == _run(argv, script).stdout


def test_an_external_pack_plays_over_the_cli(tmp_path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "pack.toml").write_text('name = "closet"\n', encoding="utf-8")
    (tmp_path / "areas.toml").write_text(
        '[[grid]]\narea = "closet"\nrows = """\n...\n"""\n', encoding="utf-8"
    )
    (tmp_path / "entities.toml").write_text(
        '[[entity]]\nid = "player"\nposition = "closet:0,0"\nblocker = true\n'
        "[entity.actor]\nname = 'Mote'\nhp = 5\nmax_hp = 5\n",
        encoding="utf-8",
    )
    result = _run(["--pack", str(tmp_path)], "move east\nquit\n")
    assert result.returncode == 0
    assert "closet" in result.stdout


def test_a_broken_external_pack_fails_cleanly(tmp_path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "pack.toml").write_text('name = "broken"\n', encoding="utf-8")
    result = _run(["--pack", str(tmp_path)], "")
    assert result.returncode == 2
    assert "areas.toml" in result.stderr


def test_help_is_available_without_playing() -> None:
    result = subprocess.run(
        _SCRIPT + ["--help"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    assert "--frontend" in result.stdout
    assert "--seed" in result.stdout


def test_record_then_replay_verifies_over_the_cli(tmp_path) -> None:  # type: ignore[no-untyped-def]
    recording = tmp_path / "run.gwr"
    played = _run(
        ["--record", str(recording)], "move east\nmove east\nmove south\nquit\n"
    )
    assert played.returncode == 0
    verified = _run(["--replay", str(recording)], "")
    assert verified.returncode == 0
    assert "recording verified: 3 steps" in verified.stdout


def test_a_tampered_recording_fails_replay_over_the_cli(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import json

    recording = tmp_path / "run.gwr"
    _run(["--record", str(recording)], "move east\nmove east\nquit\n")
    lines = recording.read_text(encoding="utf-8").splitlines()
    doctored = json.loads(lines[1])
    doctored["command"] = "move west"
    lines[1] = json.dumps(doctored)
    recording.write_text("\n".join(lines) + "\n", encoding="utf-8")
    verified = _run(["--replay", str(recording)], "")
    assert verified.returncode == 1
    assert "diverged" in verified.stdout
