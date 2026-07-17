"""Painting: the whole screen as a pure function of the frame.

Stable regions, fixed line budgets, full repaint each turn — a byte-identical
frame paints a byte-identical screen, which is what makes golden snapshots and
PTY differential tests meaningful (design 0003 §12, §17). ASCII throughout
(ADR-007); the only ANSI used is clear-and-home.
"""

from __future__ import annotations

import textwrap

from glyphwright.frames.frame import (
    GridView,
    RoomView,
    SemanticFrame,
)

_CLEAR = "\x1b[2J\x1b[H"
_WIDTH = 78
_VIEWPORT_LINES = 9
_LOG_LINES = 6

_HINTS = (
    "[arrows/hjkl] move  [1-9] exit  [a]ttack  [t]ake  [u]se  [e]quip  "
    "[f]lee  [.]wait  [x]look  [;]command  [:]meta  [q]uit"
)


def _numbered_exits(frame: SemanticFrame) -> str:
    grammar = frame.commands
    if "move" not in grammar.verb_names():
        return ""
    domain = grammar.domains("move")[0]
    return "  ".join(f"{i + 1}) {token}" for i, token in enumerate(domain))


def _viewport_lines(frame: SemanticFrame) -> list[str]:
    viewport = frame.viewport
    if isinstance(viewport, GridView):
        lines = list(viewport.tiles)
    elif isinstance(viewport, RoomView):
        lines = [viewport.name]
        lines.extend(textwrap.wrap(viewport.description, _WIDTH))
        if viewport.contents:
            lines.append(f"You see: {', '.join(viewport.contents)}.")
    else:
        lines = ["-- battle --"]
        for actor in frame.actors:
            lines.append(f"  {actor.id:<12} {actor.hp:>3}/{actor.max_hp}")
    exits = _numbered_exits(frame)
    if exits:
        lines.append(f"exits: {exits}")
    return lines


def _status_line(frame: SemanticFrame) -> str:
    player = next((actor for actor in frame.actors if actor.id == "player"), None)
    if player is None:
        return ""
    return f"hp {player.hp}/{player.max_hp}"


def _fit(lines: list[str], budget: int) -> list[str]:
    trimmed = [line[:_WIDTH] for line in lines[:budget]]
    return trimmed + [""] * (budget - len(trimmed))


def paint(frame: SemanticFrame, log: tuple[str, ...]) -> str:
    """One full screen. Pure: same frame and log, same bytes."""
    header = f"GlyphWright · turn {frame.turn} · {frame.mode} · {frame.viewport.area}"
    lines = [header[:_WIDTH], "-" * _WIDTH]
    lines.extend(_fit(_viewport_lines(frame), _VIEWPORT_LINES))
    lines.append(_status_line(frame))
    lines.append("-" * _WIDTH)
    lines.extend(_fit(list(log[-_LOG_LINES:]), _LOG_LINES))
    lines.append("-" * _WIDTH)
    lines.append(_HINTS[:_WIDTH])
    return _CLEAR + "\r\n".join(lines) + "\r\n"
