"""Scene composition: the window's content as pure data (design 0011 §3).

``compose`` is the GUI's analogue of plain's ``project`` and the TUI's
``paint``: everything the window will show, minted from the frame alone. The
Scene is the evidence and the pixels are derived material, so this module
must never import pygame — scene goldens and projection-consistency tests run
with the ``gui`` extra absent.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass

from glyphwright.frames.frame import (
    DialogueView,
    GridView,
    LockView,
    MenuView,
    RoomView,
    SemanticFrame,
)

Color = tuple[int, int, int]

#: Character columns for prose regions; wrapping happens at compose time so
#: the Scene, not the painter, decides every line break deterministically.
TEXT_COLS = 60
LOG_LINES = 6

_DEFAULT_FG: Color = (200, 200, 200)
_PALETTE: dict[str, Color] = {
    "@": (255, 214, 64),  # the player stands out
    "#": (128, 122, 110),  # walls recede
    ".": (86, 92, 86),  # floor recedes further
    "?": (52, 52, 64),  # unseen tiles barely register (0006 §1)
}

_HINTS = (
    "[arrows/hjkl] move  [1-9] exit  [a]ttack  [t]ake  [u]se  [e]quip  [f]lee",
    "[.]wait  [x]look  [q]uit",
)


@dataclass(frozen=True, slots=True)
class Cell:
    """One glyph at one grid position, with its palette color."""

    x: int
    y: int
    glyph: str
    fg: Color


@dataclass(frozen=True, slots=True)
class Scene:
    """Everything the window shows, as data. Frozen: equal frames and logs
    compose equal Scenes, which is what the determinism tests assert."""

    turn: int
    mode: str
    area: str
    cells: tuple[Cell, ...]
    text: tuple[str, ...]
    exits: str
    status: str
    log: tuple[str, ...]
    hints: tuple[str, ...]


def _grid_cells(viewport: GridView) -> tuple[Cell, ...]:
    return tuple(
        Cell(x=x, y=y, glyph=glyph, fg=_PALETTE.get(glyph, _DEFAULT_FG))
        for y, row in enumerate(viewport.tiles)
        for x, glyph in enumerate(row)
        if glyph != " "
    )


def _room_text(viewport: RoomView) -> tuple[str, ...]:
    # Contents before the prose, as in the TUI: what the player can act on
    # must survive any region budget a painter applies.
    lines = [viewport.name]
    if viewport.contents:
        lines.append(f"You see: {', '.join(viewport.contents)}.")
    lines.extend(textwrap.wrap(viewport.description, TEXT_COLS))
    return tuple(lines)


def _placeholder_text(frame: SemanticFrame) -> tuple[str, ...]:
    # 13A covers exploration; other modes get an honest signpost, never a
    # crash (0011 §7). The mode is named so the player knows what happened.
    return (
        f"-- {frame.mode} --",
        "This mode is not yet drawn by the GUI.",
        "Play it with --frontend tui (or plain).",
    )


def _numbered_exits(frame: SemanticFrame) -> str:
    grammar = frame.commands
    if "move" not in grammar.verb_names():
        return ""
    domain = grammar.domains("move")[0]
    return "  ".join(f"{i + 1}) {token}" for i, token in enumerate(domain))


def _status(frame: SemanticFrame) -> str:
    player = next((actor for actor in frame.actors if actor.id == "player"), None)
    if player is None:
        return ""
    line = f"hp {player.hp}/{player.max_hp}"
    if player.mp is not None:
        line += f"  mp {player.mp[0]}/{player.mp[1]}"
    return line


def compose(frame: SemanticFrame, log: tuple[str, ...]) -> Scene:
    """The whole window as data. Pure: same frame and log, same Scene."""
    viewport = frame.viewport
    cells: tuple[Cell, ...] = ()
    text: tuple[str, ...] = ()
    if isinstance(viewport, GridView):
        cells = _grid_cells(viewport)
    elif isinstance(viewport, RoomView):
        text = _room_text(viewport)
    else:
        assert isinstance(viewport, MenuView | DialogueView | LockView)
        text = _placeholder_text(frame)
    return Scene(
        turn=frame.turn,
        mode=frame.mode,
        area=viewport.area,
        cells=cells,
        text=text,
        exits=_numbered_exits(frame),
        status=_status(frame),
        log=tuple(log[-LOG_LINES:]),
        hints=_HINTS,
    )


def scene_text(scene: Scene) -> str:
    """A stable text serialization of a Scene, for reviewed goldens.

    Cells are re-joined into glyph rows so the dump reads like a map; a human
    reviews this the way they review a plain transcript.
    """
    lines = [f"== turn {scene.turn} · {scene.mode} · {scene.area} =="]
    if scene.cells:
        width = max(cell.x for cell in scene.cells) + 1
        height = max(cell.y for cell in scene.cells) + 1
        rows = [[" "] * width for _ in range(height)]
        for cell in scene.cells:
            rows[cell.y][cell.x] = cell.glyph
        lines.extend("".join(row).rstrip() for row in rows)
    lines.extend(scene.text)
    if scene.exits:
        lines.append(f"exits: {scene.exits}")
    if scene.status:
        lines.append(scene.status)
    lines.extend(f"log: {entry}" for entry in scene.log)
    lines.extend(f"hint: {hint}" for hint in scene.hints)
    return "\n".join(lines) + "\n"
