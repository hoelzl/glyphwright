"""Painting: blit a Scene onto a pygame surface (design 0011 §3, §5).

Everything drawn here was decided by ``compose``; this module adds pixels,
never facts. Text uses pygame-ce's bundled font at a fixed size — no system
font lookup, no environment-dependent fallback — and the grid is monospaced
by geometry: each glyph is blitted into its own fixed cell, so alignment
never depends on font metrics. All layout comes from the Scene's own
constants (``scene``), because click zones are minted there and pixels must
land exactly where the zones are.

A tileset (0011 §5, slice 13C) is a paint-time skin: cells with a tile image
blit the image, cells without fall back to the glyph. The Scene never knows.
"""

from __future__ import annotations

from collections.abc import Mapping

import pygame

from glyphwright.frontends.gui.scene import (
    BAR_TOP,
    CELL_H,
    CELL_W,
    EXITS_TOP,
    HINTS_TOP,
    LINE_H,
    LOG_TOP,
    MARGIN,
    STATUS_TOP,
    VIEWPORT_TOP,
    Scene,
)
from glyphwright.frontends.gui.scene import (
    WINDOW_SIZE as WINDOW_SIZE,  # re-exported: the session and tests size by it
)

_FONT_SIZE = 20

_BG = (16, 16, 20)
_HEADER_FG = (232, 226, 205)
_TEXT_FG = (200, 200, 200)
_STATUS_FG = (255, 214, 64)
_LOG_FG = (150, 150, 160)
_HINT_FG = (110, 110, 122)

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


def paint(
    scene: Scene,
    surface: pygame.Surface,
    tiles: Mapping[str, pygame.Surface] | None = None,
) -> None:
    """Draw the whole Scene. Same scene and tiles, same surface bytes."""
    surface.fill(_BG)
    header = f"GlyphWright · turn {scene.turn} · {scene.mode} · {scene.area}"
    _text(surface, header, (MARGIN, MARGIN), _HEADER_FG)

    for cell in scene.cells:
        at = (MARGIN + cell.x * CELL_W, VIEWPORT_TOP + cell.y * CELL_H)
        tile = None if tiles is None else tiles.get(cell.glyph)
        if tile is not None:
            surface.blit(tile, at)
        else:
            _text(surface, cell.glyph, at, cell.fg)
    for index, line in enumerate(scene.text):
        _text(surface, line, (MARGIN, VIEWPORT_TOP + index * LINE_H), _TEXT_FG)

    # Exit labels render at their click zones, one per slot: the zone and the
    # pixels come from the same target, so they cannot disagree.
    slots = [target for target in scene.targets if target.kind == "exit"]
    if slots:
        _text(surface, "exits:", (MARGIN, EXITS_TOP), _TEXT_FG)
        for slot in slots:
            _text(surface, slot.label, (slot.x, slot.y), _TEXT_FG)
    if scene.status:
        _text(surface, scene.status, (MARGIN, STATUS_TOP), _STATUS_FG)
    for index, entry in enumerate(scene.log):
        _text(surface, entry, (MARGIN, LOG_TOP + index * LINE_H), _LOG_FG)
    for index, hint in enumerate(scene.hints):
        _text(surface, hint, (MARGIN, HINTS_TOP + index * LINE_H), _HINT_FG)
    if scene.bar is not None:
        _text(surface, scene.bar + "_", (MARGIN, BAR_TOP), _HEADER_FG)
