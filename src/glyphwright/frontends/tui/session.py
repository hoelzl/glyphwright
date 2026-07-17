"""The TUI loop: paint, read one key, step, repeat.

Turn-based to its foundations: input blocks, nothing repaints until the world
changes, and the loop itself holds no game state beyond the rolling message
log (whose length is presentation, not semantics).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TextIO

from glyphwright.api import Engine
from glyphwright.frontends.tui import keys, render
from glyphwright.frontends.wire import decode_command
from glyphwright.harness import meta

_ALT_SCREEN_ON = "\x1b[?1049h\x1b[?25l"
_ALT_SCREEN_OFF = "\x1b[?25h\x1b[?1049l"


def _read_line(key_source: Iterator[str], output: TextIO, prompt: str) -> str:
    """Collect typed characters until Enter, echoing as they come."""
    output.write(prompt)
    output.flush()
    collected: list[str] = []
    for key in key_source:
        if key in ("\r", "\n"):
            break
        if key in ("\x08", "\x7f"):
            if collected:
                collected.pop()
                output.write("\x08 \x08")
            continue
        collected.append(key)
        output.write(key)
        output.flush()
    return "".join(collected)


def run_session(
    engine: Engine,
    key_source: Iterator[str] | None,
    output: TextIO,
    *,
    harness: bool = False,
) -> int:
    """Drive a run as a full-screen session.

    ``key_source`` is any iterator of key names; ``None`` reads the real
    keyboard. Scripted iterators make the loop testable without a PTY.
    """
    source = key_source if key_source is not None else keys.read_keys()
    log: list[str] = []
    output.write(_ALT_SCREEN_ON)
    try:
        while True:
            output.write(render.paint(engine.frame(), tuple(log)))
            output.flush()
            try:
                key = next(source)
            except StopIteration:
                return 0
            if key == "q":
                return 0

            if key == ";":
                text = _read_line(source, output, "> ")
                command = decode_command(text)
                if command is None:
                    log.append(f"? unparsable: {text!r}")
                    continue
            elif key == ":":
                if not harness:
                    log.append("? the meta-channel needs --harness")
                    continue
                text = _read_line(source, output, ": ")
                payload = meta.handle(engine, f":{text}")
                log.extend(meta.render_text(payload).splitlines())
                continue
            else:
                maybe = keys.translate(key, engine.frame())
                if maybe is None:
                    continue
                command = maybe

            result = engine.step(command)
            if result.rejection is not None:
                log.append(f"? {result.rejection.reason}: {result.rejection.hint}")
            else:
                log.extend(result.frame.messages)
    finally:
        output.write(_ALT_SCREEN_OFF)
        output.flush()
