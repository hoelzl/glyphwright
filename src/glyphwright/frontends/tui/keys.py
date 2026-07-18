"""Terminal key decoding, plus the shared translation table.

``translate`` lives in :mod:`glyphwright.frontends.keymap` — one binding table
for every interactive frontend (0011 §4) — and is re-exported here for the
TUI's callers. This module owns only what is terminal-specific: normalizing
raw POSIX and Windows console input into key names.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator

from glyphwright.frontends.keymap import translate

__all__ = ["decode_posix", "decode_windows", "read_keys", "translate"]


_CSI_ARROWS = {"A": "UP", "B": "DOWN", "D": "LEFT", "C": "RIGHT"}
_SCAN_ARROWS = {"H": "UP", "P": "DOWN", "K": "LEFT", "M": "RIGHT"}


def decode_posix(read: Callable[[], str]) -> Iterator[str]:
    """Normalize a raw POSIX character stream into key names.

    A CSI sequence (``ESC [ … final``) is consumed whole — parameter bytes
    like the ``1;5`` of Ctrl-arrow never leak as individual keys — and only
    plain arrows map to names; other sequences yield nothing. A bare ESC
    yields ``"ESC"`` without swallowing whatever follows it.
    """
    while True:
        ch = read()
        if not ch:
            return
        if ch != "\x1b":
            yield ch
            continue
        follow = read()
        if follow != "[":
            yield "ESC"
            if follow:
                yield follow
            continue
        parameters = ""
        final = read()
        while final and not ("\x40" <= final <= "\x7e"):
            parameters += final
            final = read()
        # Only unmodified arrows map to names; a modified arrow (ESC[1;5C)
        # shares the final byte but carries parameters, and means nothing.
        if not parameters:
            mapped = _CSI_ARROWS.get(final, "")
            if mapped:
                yield mapped


def decode_windows(
    getwch: Callable[[], str], key_pending: Callable[[], bool]
) -> Iterator[str]:
    """Normalize a ``msvcrt`` character stream into key names.

    ``'\\x00'``/``'\\xe0'`` are extended-key prefixes only when the scan code
    is already pending — a genuinely typed ``'à'`` (U+00E0, a real key on
    AZERTY keyboards) arrives alone and passes through as itself.
    """
    while True:
        ch = getwch()
        if ch in ("\x00", "\xe0") and key_pending():
            yield _SCAN_ARROWS.get(getwch(), "")
        else:
            yield ch


def read_keys() -> Iterator[str]:  # pragma: no cover - real keyboards only
    """Blocking keystrokes from the real terminal, arrows normalized.

    Tests and scripted sessions inject their own iterator instead; this
    generator is the only code that touches a physical keyboard. On POSIX the
    terminal is restored in a ``finally`` — callers must ``close()`` the
    generator when they unwind, or the shell is left in raw mode.
    """
    if sys.platform == "win32":
        import msvcrt

        yield from decode_windows(msvcrt.getwch, msvcrt.kbhit)
    else:
        import termios
        import tty

        fd = sys.stdin.fileno()
        saved = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            yield from decode_posix(lambda: sys.stdin.read(1))
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)
