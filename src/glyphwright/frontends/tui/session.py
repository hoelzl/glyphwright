"""The TUI loop: paint, read one key, step, repeat.

Turn-based to its foundations: input blocks, nothing repaints until the world
changes, and the loop itself holds no game state beyond the rolling message
log (whose length is presentation, not semantics).
"""

from __future__ import annotations

import textwrap
from collections.abc import Iterator
from typing import TextIO

from glyphwright.api import Engine
from glyphwright.frontends.tui import keys, render
from glyphwright.frontends.wire import decode_command
from glyphwright.harness import meta

_ALT_SCREEN_ON = "\x1b[?1049h\x1b[?25l"
_ALT_SCREEN_OFF = "\x1b[?25h\x1b[?1049l"


def _enable_vt() -> None:  # pragma: no cover - real consoles only
    """Turn on VT processing for legacy Windows consoles.

    Modern terminals already interpret ANSI; this makes the classic conhost
    behave. A no-op everywhere else, and harmless when it fails.
    """
    import sys

    # Positive-guard block form: mypy skips a non-matching sys.platform block
    # instead of flagging it unreachable, so this checks on every platform.
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # VT processing


def _read_line(key_source: Iterator[str], output: TextIO, prompt: str) -> str | None:
    """Collect typed characters until Enter, echoing as they come.

    ``None`` means the bar was cancelled (Escape or Ctrl-C). Named keys like
    ``UP`` and other control characters are ignored rather than spliced into
    the text.
    """
    output.write(prompt)
    output.flush()
    collected: list[str] = []
    for key in key_source:
        if key in ("\r", "\n"):
            break
        if key in ("\x03", "ESC"):
            return None
        if key in ("\x08", "\x7f"):
            if collected:
                collected.pop()
                output.write("\x08 \x08")
                output.flush()
            continue
        if len(key) != 1 or key < " ":
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
    if key_source is None:  # pragma: no cover - real terminals only
        _enable_vt()
        source = keys.read_keys()
    else:
        source = key_source
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
            if key in ("q", "\x03"):
                # Raw mode swallows the Ctrl-C signal; honour the intent.
                return 0

            if key == ";":
                text = _read_line(source, output, "> ")
                if text is None:
                    continue
                command = decode_command(text)
                if command is None:
                    log.append(f"? unparsable: {text!r}")
                    continue
            elif key == ":":
                if not harness:
                    log.append("? the meta-channel needs --harness")
                    continue
                text = _read_line(source, output, ": ")
                if text is None:
                    continue
                payload = meta.handle(engine, f":{text}")
                for line in meta.render_text(payload).splitlines():
                    # The log region truncates at its width; wrap instead of
                    # silently cutting a ':frame' dump short.
                    log.extend(textwrap.wrap(line, render.WIDTH) or [""])
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
        # Closing the source runs the reader's own finally, restoring the
        # POSIX terminal from raw mode before any traceback prints.
        close = getattr(source, "close", None)
        if close is not None:
            close()
        output.write(_ALT_SCREEN_OFF)
        output.flush()
