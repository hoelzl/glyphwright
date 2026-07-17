"""Keystroke translation: keys exist only here, commands exist everywhere.

``translate`` maps one key against the frame's grammar and returns a kernel
command or ``None`` — a hotkey whose verb is not advertised does nothing,
so the keyboard can never say something the grammar cannot (0003 §6).
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator

from glyphwright.frames.frame import SemanticFrame
from glyphwright.kernel.commands import (
    Abort,
    Attack,
    Choose,
    Command,
    Equip,
    Flee,
    Look,
    Move,
    Pick,
    Take,
    Use,
    Wait,
)

_DIRECTIONS = {
    "UP": "north",
    "DOWN": "south",
    "LEFT": "west",
    "RIGHT": "east",
    "k": "north",
    "j": "south",
    "h": "west",
    "l": "east",
}

_FIRST_OF_DOMAIN: dict[str, tuple[str, Callable[[str], Command]]] = {
    "t": ("take", Take),
    "u": ("use", Use),
    "e": ("equip", Equip),
    "a": ("attack", Attack),
}


def translate(key: str, frame: SemanticFrame) -> Command | None:
    """One key against the frame's grammar; ``None`` when it means nothing."""
    grammar = frame.commands
    names = grammar.verb_names()

    if key in _DIRECTIONS and "move" in names:
        token = _DIRECTIONS[key]
        if token in grammar.domains("move")[0]:
            return Move(token)
        return None
    # Explicit ASCII digits only: exotic keys like '²' satisfy isdigit() but
    # are not exit choices, and must never crash the session.
    if key in "123456789" and "choose" in names:
        domain = grammar.domains("choose")[0]
        if key in domain:
            return Choose(key)
        return None
    if key in "123456789" and "move" in names:
        domain = grammar.domains("move")[0]
        index = int(key) - 1
        if index < len(domain):
            return Move(domain[index])
        return None
    if key in _FIRST_OF_DOMAIN:
        verb, builder = _FIRST_OF_DOMAIN[key]
        if verb in names:
            return builder(grammar.domains(verb)[0][0])
        return None
    if key == "f" and "flee" in names:
        return Flee()
    if key == "p" and "pick" in names:
        return Pick()
    if key == "z" and "abort" in names:
        return Abort()
    if key in (".", " ") and "wait" in names:
        return Wait()
    if key == "x" and "look" in names:
        return Look()
    return None


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
