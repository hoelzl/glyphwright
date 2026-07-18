"""Painting: blit a Scene onto a pygame surface (design 0011 §3, §5).

Everything drawn here was decided by ``compose``; this module adds pixels,
never facts. Text uses pygame-ce's bundled font at a fixed size — no system
font lookup, no environment-dependent fallback — and the grid is monospaced
by geometry: each glyph is blitted into its own fixed cell, so alignment
never depends on font metrics.
"""

from __future__ import annotations

import pygame

from glyphwright.frontends.gui.scene import Scene

CELL_W = 16
CELL_H = 24
_MARGIN = 12
_LINE_H = 22
_FONT_SIZE = 20

WINDOW_SIZE = (960, 600)

_BG = (16, 16, 20)
_HEADER_FG = (232, 226, 205)
_TEXT_FG = (200, 200, 200)
_STATUS_FG = (255, 214, 64)
_LOG_FG = (150, 150, 160)
_HINT_FG = (110, 110, 122)

#: Grid rows start below the header; text-viewport lines share the region.
_VIEWPORT_TOP = _MARGIN + _LINE_H + 8
#: The lower regions sit at fixed rows, like the TUI's region budgets: a tall
#: viewport can never push the player's options off the window.
_EXITS_TOP = _VIEWPORT_TOP + 9 * CELL_H + 8
_STATUS_TOP = _EXITS_TOP + _LINE_H
_LOG_TOP = _STATUS_TOP + _LINE_H + 8
_HINTS_TOP = _LOG_TOP + 6 * _LINE_H + 8
_BAR_TOP = _HINTS_TOP + 2 * _LINE_H + 8

_font: pygame.font.Font | None = None


def _get_font() -> pygame.font.Font:
    global _font
    if _font is None:
        if not pygame.font.get_init():
            pygame.font.init()
        # Font(None, …) is the bundled freesansbold: identical bytes in every
        # environment the same pygame-ce wheel reaches.
        _font = pygame.font.Font(None, _FONT_SIZE)
    return _font


def _text(surface: pygame.Surface, line: str, at: tuple[int, int], fg: object) -> None:
    surface.blit(_get_font().render(line, True, fg), at)  # type: ignore[arg-type]


def paint(scene: Scene, surface: pygame.Surface) -> None:
    """Draw the whole Scene. Same scene, same surface bytes."""
    surface.fill(_BG)
    header = f"GlyphWright · turn {scene.turn} · {scene.mode} · {scene.area}"
    _text(surface, header, (_MARGIN, _MARGIN), _HEADER_FG)

    for cell in scene.cells:
        _text(
            surface,
            cell.glyph,
            (_MARGIN + cell.x * CELL_W, _VIEWPORT_TOP + cell.y * CELL_H),
            cell.fg,
        )
    for index, line in enumerate(scene.text):
        _text(surface, line, (_MARGIN, _VIEWPORT_TOP + index * _LINE_H), _TEXT_FG)

    if scene.exits:
        _text(surface, f"exits: {scene.exits}", (_MARGIN, _EXITS_TOP), _TEXT_FG)
    if scene.status:
        _text(surface, scene.status, (_MARGIN, _STATUS_TOP), _STATUS_FG)
    for index, entry in enumerate(scene.log):
        _text(surface, entry, (_MARGIN, _LOG_TOP + index * _LINE_H), _LOG_FG)
    for index, hint in enumerate(scene.hints):
        _text(surface, hint, (_MARGIN, _HINTS_TOP + index * _LINE_H), _HINT_FG)
    if scene.bar is not None:
        _text(surface, scene.bar + "_", (_MARGIN, _BAR_TOP), _HEADER_FG)
