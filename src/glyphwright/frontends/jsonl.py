"""The JSONL frontend: one JSON object per line over stdio.

The lowest-friction transport for agents and out-of-process verification:
process isolation with full semantic observations and no ANSI parsing.
"""

from __future__ import annotations

from typing import TextIO

from glyphwright.api import Engine
from glyphwright.frontends.wire import (
    REJECTION_SCHEMA,
    canonical_json,
    decode_command,
    encode_event,
    encode_frame,
    encode_rejection,
    missing_argument_hint,
)
from glyphwright.harness import meta


def safe_echo(line: str) -> str:
    """The input line, stripped, with undecodable bytes as ``\\xNN`` escapes.

    v0 finding H6: undecodable bytes reach Python as lone surrogates (the CLI
    reads stdin with ``surrogateescape``), and echoing them produced output no
    UTF-8 consumer could read. Frontends apply this to every line as they read
    it, before anything parses it, so no later echo can leak a raw byte.
    """
    raw = line.strip().encode("utf-8", "surrogateescape")
    return raw.decode("utf-8", "backslashreplace")


def _rejection(engine: Engine, line: str, reason: str, hint: str) -> dict[str, object]:
    return {
        "schema": REJECTION_SCHEMA,
        "turn": engine.frame().turn,
        "command": line,
        "reason": reason,
        "hint": hint,
    }


def unparsable_hint(engine: Engine) -> str:
    """What the engine accepts right now, from the frame's own grammar.

    v0 finding H7: the hint was a hard-coded list that fell behind the
    command language as verbs were added.
    """
    return "expected one of: " + ", ".join(
        (*engine.frame().commands.verb_names(), "quit")
    )


def run_session(
    engine: Engine, input_stream: TextIO, output: TextIO, *, harness: bool = False
) -> int:
    """Speak JSONL: a session header, then a frame per command."""
    _emit(output, engine.fingerprint().header(harness=harness))
    _emit(output, encode_frame(engine.frame()))

    while True:
        raw = input_stream.readline()
        line = safe_echo(raw)
        if not raw or line == "quit":
            return 0

        if line.startswith(":"):
            if not harness:
                _emit(
                    output,
                    _rejection(
                        engine,
                        line,
                        "harness_disabled",
                        "start the session with --harness",
                    ),
                )
                continue
            _emit(output, meta.handle(engine, line))
            continue

        command = decode_command(line)
        if command is None:
            hint = missing_argument_hint(engine.frame(), line) or unparsable_hint(
                engine
            )
            _emit(output, _rejection(engine, line, "unparsable", hint))
            continue

        result = engine.step(command)
        if result.rejection is not None:
            _emit(output, encode_rejection(result.rejection, turn=result.frame.turn))
            continue
        for event in result.events:
            _emit(output, encode_event(event, turn=result.frame.turn))
        _emit(output, encode_frame(result.frame))


def _emit(output: TextIO, payload: dict[str, object]) -> None:
    output.write(canonical_json(payload) + "\n")
    output.flush()
