"""Tileset loading: a pack-optional glyph→image table (design 0011 §5, 13C).

A pack may ship ``tileset.toml`` with a ``[glyphs]`` table mapping single
glyphs to image files relative to the pack root. The tileset is a paint-time
skin: the engine and the pack loader never see it, the Scene still speaks
glyphs, and any glyph without an entry falls back to font rendering. A
declared table that cannot be honoured is an error — the player asked for
tiles with ``--tiles`` and silence would misrepresent what they see.
"""

from __future__ import annotations

import tomllib
from importlib.resources.abc import Traversable

import pygame

from glyphwright.frontends.gui.scene import CELL_H, CELL_W

_TABLE = "tileset.toml"


class TilesetError(Exception):
    """A tileset table that cannot be honoured, with a located message."""


def load_tileset(root: Traversable) -> dict[str, pygame.Surface] | None:
    """The pack's tiles, scaled to cell size; ``None`` when it ships none."""
    table = root / _TABLE
    if not table.is_file():
        return None
    try:
        data = tomllib.loads(table.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise TilesetError(f"{_TABLE}: {error}") from error
    glyphs = data.get("glyphs")
    if not isinstance(glyphs, dict) or not glyphs:
        raise TilesetError(f"{_TABLE}: a [glyphs] table is required")
    tiles: dict[str, pygame.Surface] = {}
    for glyph, filename in glyphs.items():
        if len(glyph) != 1:
            raise TilesetError(f"{_TABLE}: {glyph!r} is not a single glyph")
        if not isinstance(filename, str):
            raise TilesetError(f"{_TABLE}: {glyph!r} must name an image file")
        image = root / filename
        try:
            with image.open("rb") as source:
                loaded = pygame.image.load(source, filename)
        except (OSError, pygame.error) as error:
            raise TilesetError(f"{_TABLE}: {glyph!r} → {filename}: {error}") from error
        tiles[glyph] = pygame.transform.scale(loaded, (CELL_W, CELL_H))
    return tiles
