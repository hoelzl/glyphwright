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
    Attack,
    Command,
    Equip,
    Flee,
    Look,
    Move,
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
    if key.isdigit() and key != "0" and "move" in names:
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
    if key in (".", " ") and "wait" in names:
        return Wait()
    if key == "x" and "look" in names:
        return Look()
    return None


def read_keys() -> Iterator[str]:  # pragma: no cover - real keyboards only
    """Blocking keystrokes from the real terminal, arrows normalized.

    Tests and scripted sessions inject their own iterator instead; this
    generator is the only code that touches a physical keyboard.
    """
    if sys.platform == "win32":
        import msvcrt

        arrows = {"H": "UP", "P": "DOWN", "K": "LEFT", "M": "RIGHT"}
        while True:
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):
                yield arrows.get(msvcrt.getwch(), "")
            else:
                yield ch
    else:
        import termios
        import tty

        arrows = {"A": "UP", "B": "DOWN", "D": "LEFT", "C": "RIGHT"}
        fd = sys.stdin.fileno()
        saved = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            while True:
                ch = sys.stdin.read(1)
                if ch == "\x1b" and sys.stdin.read(1) == "[":
                    yield arrows.get(sys.stdin.read(1), "")
                else:
                    yield ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)
