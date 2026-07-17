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
    assert "glyphwright.event/5" in schemas
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


def test_help_is_available_without_playing() -> None:
    result = subprocess.run(
        _SCRIPT + ["--help"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    assert "--frontend" in result.stdout
    assert "--seed" in result.stdout
