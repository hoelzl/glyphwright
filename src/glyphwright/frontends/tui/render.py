"""Painting: the whole screen as a pure function of the frame.

Stable regions, fixed line budgets, full repaint each turn — a byte-identical
frame paints a byte-identical screen, which is what makes golden snapshots and
PTY differential tests meaningful (design 0003 §12, §17). ASCII throughout
(ADR-007); the only ANSI used is clear-and-home.
"""

from __future__ import annotations

import textwrap

from glyphwright.frames.frame import (
    DialogueView,
    GridView,
    LockView,
    MenuView,
    RoomView,
    SemanticFrame,
)

_CLEAR = "\x1b[2J\x1b[H"
WIDTH = 78
_WIDTH = WIDTH
_VIEWPORT_LINES = 9
_LOG_LINES = 6

_HINTS = (
    "[arrows/hjkl] move  [1-9] exit  [a]ttack  [t]ake  [u]se  [e]quip  [f]lee",
    "[.]wait  [x]look  [;]command  [:]meta  [q]uit",
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
        # Contents come before the prose: a long description may be truncated
        # by the region budget, but what the player can act on may not.
        lines = [viewport.name]
        if viewport.contents:
            lines.append(f"You see: {', '.join(viewport.contents)}.")
        lines.extend(textwrap.wrap(viewport.description, _WIDTH))
    elif isinstance(viewport, DialogueView):
        # Choices own the region's tail: long prose truncates, options never.
        budget = _VIEWPORT_LINES - 1
        prose_room = max(1, budget - 1 - len(viewport.choices))
        lines = [f"{viewport.speaker}:"]
        lines.extend(textwrap.wrap(viewport.text, _WIDTH - 2)[:prose_room])
        for index, choice in enumerate(viewport.choices):
            lines.append(f"  {index + 1}) {choice}")
    elif isinstance(viewport, LockView):
        drawn = "*" * viewport.pins + "." * (viewport.total - viewport.pins)
        lines = [
            f"-- lockpicking: {viewport.target} --",
            f"pins: [{drawn}]",
            "[p]ick the next pin, [z] to abort",
        ]
    else:
        assert isinstance(viewport, MenuView)
        lines = ["-- battle --"]
        for actor in frame.actors:
            lines.append(f"  {actor.id:<12} {actor.hp:>3}/{actor.max_hp}")
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
    # The exits line owns the region's last row, so a tall viewport can never
    # push the player's movement options off the screen.
    lines.extend(_fit(_viewport_lines(frame), _VIEWPORT_LINES - 1))
    exits = _numbered_exits(frame)
    lines.append(f"exits: {exits}"[:_WIDTH] if exits else "")
    lines.append(_status_line(frame))
    lines.append("-" * _WIDTH)
    lines.extend(_fit(list(log[-_LOG_LINES:]), _LOG_LINES))
    lines.append("-" * _WIDTH)
    lines.extend(hint[:_WIDTH] for hint in _HINTS)
    return _CLEAR + "\r\n".join(lines) + "\r\n"
