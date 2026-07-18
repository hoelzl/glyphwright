"""Regenerate the reference pack's tileset images (design 0011 §5, 13C).

Like ``regenerate_goldens.py``, this is run by humans after a deliberate art
change, and the diff is reviewed by eye before committing:

    uv --no-config run python tests/regenerate_tiles.py

Each tile is a flat background plus one simple shape at cell size — enough to
prove the tileset path end to end without pretending to be art. The table
here is the single source for both the images and ``tileset.toml``.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402

CELL = (16, 24)
PACK_DIR = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "glyphwright"
    / "content"
    / "packs"
    / "reference-vale"
)

_DARK = (24, 26, 24)

#: glyph -> (filename stem, background, shape, shape color)
TILES: dict[str, tuple[str, tuple[int, int, int], str, tuple[int, int, int]]] = {
    "#": ("wall", (70, 66, 60), "block", (128, 122, 110)),
    ".": ("floor", _DARK, "dot", (86, 92, 86)),
    "@": ("player", _DARK, "disc", (255, 214, 64)),
    "!": ("potion", _DARK, "box", (200, 60, 60)),
    "/": ("sword", _DARK, "slash", (180, 190, 200)),
    "g": ("goblin", _DARK, "disc", (90, 170, 70)),
    "b": ("bandit", _DARK, "disc", (170, 90, 60)),
    "+": ("door", _DARK, "box", (150, 110, 60)),
    "O": ("cask", _DARK, "disc", (140, 130, 110)),
    "M": ("mystic", _DARK, "disc", (150, 90, 180)),
    "H": ("hermit", _DARK, "disc", (90, 150, 180)),
    "t": ("table", _DARK, "box", (120, 95, 60)),
    "?": ("unseen", (10, 10, 12), "dot", (52, 52, 64)),
}


def _draw(
    background: tuple[int, int, int], shape: str, fg: tuple[int, int, int]
) -> pygame.Surface:
    surface = pygame.Surface(CELL)
    surface.fill(background)
    width, height = CELL
    center = (width // 2, height // 2)
    if shape == "block":
        surface.fill(fg, pygame.Rect(1, 1, width - 2, height - 2))
    elif shape == "dot":
        surface.fill(fg, pygame.Rect(center[0] - 1, center[1] - 1, 2, 2))
    elif shape == "disc":
        pygame.draw.circle(surface, fg, center, 6)
    elif shape == "box":
        pygame.draw.rect(surface, fg, pygame.Rect(3, 6, width - 6, height - 12))
    else:
        assert shape == "slash"
        pygame.draw.line(surface, fg, (3, height - 4), (width - 4, 3), 2)
    return surface


def main() -> None:  # pragma: no cover - invoked by humans
    tile_dir = PACK_DIR / "tiles"
    tile_dir.mkdir(exist_ok=True)
    lines = ["[glyphs]"]
    for glyph, (stem, background, shape, fg) in TILES.items():
        pygame.image.save(_draw(background, shape, fg), tile_dir / f"{stem}.png")
        lines.append(f'"{glyph}" = "tiles/{stem}.png"')
        print(f"wrote tiles/{stem}.png")
    (PACK_DIR / "tileset.toml").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )
    print("wrote tileset.toml")


if __name__ == "__main__":  # pragma: no cover
    main()
