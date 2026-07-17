"""The JSONL frontend: one JSON object per line over stdio.

Lowest-friction transport for agents and out-of-process verification. Process
isolation with full semantic observations and no ANSI parsing — the expected
workhorse mode (design 0003 sections 12 and 16.3).
"""

from __future__ import annotations

import json
from typing import TextIO

from glyphwright.api import Engine
from glyphwright.frontends.wire import (
    decode_command,
    encode_event,
    encode_frame,
    encode_rejection,
)


def run_session(
    engine: Engine, input_stream: TextIO, output: TextIO, *, harness: bool = False
) -> int:
    """Speak JSONL: a session header, then a frame per command."""
    _emit(output, engine.fingerprint().header(harness=harness))
    _emit(output, encode_frame(engine.frame()))

    while True:
        line = input_stream.readline()
        if not line or line.strip() == "quit":
            return 0

        command = decode_command(line)
        if command is None:
            _emit(
                output,
                {
                    "schema": "glyphwright.rejection/1",
                    "turn": engine.frame().turn,
                    "command": line.strip(),
                    "reason": "unparsable",
                    "hint": "expected: move <exit> | look | wait | quit",
                },
            )
            continue

        result = engine.step(command)
        if result.rejection is not None:
            _emit(output, encode_rejection(result.rejection, turn=result.frame.turn))
            continue
        for event in result.events:
            _emit(output, encode_event(event, turn=result.frame.turn))
        _emit(output, encode_frame(result.frame))


def _emit(output: TextIO, payload: dict[str, object]) -> None:
    output.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    output.flush()
