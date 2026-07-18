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
from glyphwright.kernel.commands import Attack, Choose, Command, Move, Pick

Color = tuple[int, int, int]

#: Character columns for prose regions; wrapping happens at compose time so
#: the Scene, not the painter, decides every line break deterministically.
TEXT_COLS = 60
LOG_LINES = 6

# Window geometry lives here, not in paint: click targets are minted at
# compose time as pure data (0011 §4), so the layout every region — and every
# click zone — uses must be importable without pygame. paint consumes these.
MARGIN = 12
LINE_H = 22
CELL_W = 16
CELL_H = 24
WINDOW_SIZE = (960, 600)
VIEWPORT_TOP = MARGIN + LINE_H + 8
#: The lower regions sit at fixed rows, like the TUI's region budgets: a tall
#: viewport can never push the player's options off the window.
EXITS_TOP = VIEWPORT_TOP + 9 * CELL_H + 8
STATUS_TOP = EXITS_TOP + LINE_H
LOG_TOP = STATUS_TOP + LINE_H + 8
HINTS_TOP = LOG_TOP + 6 * LINE_H + 8
BAR_TOP = HINTS_TOP + 2 * LINE_H + 8
#: Exit tokens sit in fixed-width slots so their click zones are exact
#: geometry, independent of any font metric.
EXIT_SLOT_X = MARGIN + 64
EXIT_SLOT_W = 120
#: Clickable text rows (menu combatants, dialogue choices) span this width.
ROW_W = 360

_DEFAULT_FG: Color = (200, 200, 200)
_PALETTE: dict[str, Color] = {
    "@": (255, 214, 64),  # the player stands out
    "#": (128, 122, 110),  # walls recede
    ".": (86, 92, 86),  # floor recedes further
    "?": (52, 52, 64),  # unseen tiles barely register (0006 §1)
}

_HINTS = (
    "[arrows/hjkl] move  [1-9] exit/choice  [a]ttack  [t]ake  [u]se  [e]quip",
    "[f]lee  [p]ick  [z]abort  [.]wait  [x]look  [;]command  [:]meta  [q]uit",
)


@dataclass(frozen=True, slots=True)
class Cell:
    """One glyph at one grid position, with its palette color."""

    x: int
    y: int
    glyph: str
    fg: Color


@dataclass(frozen=True, slots=True)
class ClickTarget:
    """One clickable zone and the semantic command it advertises.

    Minted from the frame's grammar at compose time, so the mouse — like the
    keyboard — can never say something the grammar cannot (ADR-003, 0011 §4).
    ``kind`` tells the painter whether it also draws the label ("exit" slots)
    or the zone overlays content that is already drawn ("cell", "row").
    """

    x: int
    y: int
    w: int
    h: int
    command: Command
    label: str = ""
    kind: str = "row"


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
    #: The typed bar's echo while the player types; transient input state,
    #: shown in the window but excluded from golden evidence (0011 §4).
    bar: str | None = None
    #: Clickable zones; derived from the grammar and the layout constants,
    #: excluded from golden evidence like every other input affordance.
    targets: tuple[ClickTarget, ...] = ()


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


def _menu_text(frame: SemanticFrame) -> tuple[str, ...]:
    # Combatant summaries live in the frame's actors (0003 §10.1).
    lines = ["-- battle --"]
    lines.extend(
        f"  {actor.id:<12} {actor.hp:>3}/{actor.max_hp}" for actor in frame.actors
    )
    return tuple(lines)


def _dialogue_text(viewport: DialogueView) -> tuple[str, ...]:
    lines = list(textwrap.wrap(f"{viewport.speaker}: {viewport.text}", TEXT_COLS))
    lines.extend(
        f"  {index + 1}) {choice}" for index, choice in enumerate(viewport.choices)
    )
    return tuple(lines)


def _lock_text(viewport: LockView) -> tuple[str, ...]:
    drawn = "*" * viewport.pins + "." * (viewport.total - viewport.pins)
    return (
        f"-- lockpicking: {viewport.target} --",
        f"pins: [{drawn}]  {viewport.pins}/{viewport.total}",
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


_CARDINALS = {"north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0)}


def _row_target(row: int, command: Command) -> ClickTarget:
    return ClickTarget(
        x=MARGIN, y=VIEWPORT_TOP + row * LINE_H, w=ROW_W, h=LINE_H, command=command
    )


def _cell_targets(frame: SemanticFrame, viewport: GridView) -> list[ClickTarget]:
    """Clicking a cell next to the player moves there, when the grammar
    allows the direction."""
    player = next((actor for actor in frame.actors if actor.id == "player"), None)
    if player is None or player.at.area != viewport.area:
        return []
    if "move" not in frame.commands.verb_names():
        return []
    x_text, _, y_text = player.at.local.partition(",")
    col = int(x_text) - viewport.origin[0]
    row = int(y_text) - viewport.origin[1]
    domain = frame.commands.domains("move")[0]
    targets = []
    for token, (dx, dy) in _CARDINALS.items():
        if token not in domain:
            continue
        cx, cy = col + dx, row + dy
        if 0 <= cy < len(viewport.tiles) and 0 <= cx < len(viewport.tiles[cy]):
            targets.append(
                ClickTarget(
                    x=MARGIN + cx * CELL_W,
                    y=VIEWPORT_TOP + cy * CELL_H,
                    w=CELL_W,
                    h=CELL_H,
                    command=Move(token),
                    kind="cell",
                )
            )
    return targets


def _exit_slot_targets(frame: SemanticFrame) -> list[ClickTarget]:
    """Every advertised exit as a fixed-width slot on the exits row; the
    painter draws these labels, so zones and pixels cannot disagree."""
    if "move" not in frame.commands.verb_names():
        return []
    return [
        ClickTarget(
            x=EXIT_SLOT_X + index * EXIT_SLOT_W,
            y=EXITS_TOP,
            w=EXIT_SLOT_W - 8,
            h=LINE_H,
            command=Move(token),
            label=f"{index + 1}) {token}",
            kind="exit",
        )
        for index, token in enumerate(frame.commands.domains("move")[0])
    ]


def _targets(frame: SemanticFrame, text: tuple[str, ...]) -> tuple[ClickTarget, ...]:
    viewport = frame.viewport
    names = frame.commands.verb_names()
    targets: list[ClickTarget] = []
    if isinstance(viewport, GridView):
        targets.extend(_cell_targets(frame, viewport))
    elif isinstance(viewport, MenuView) and "attack" in names:
        domain = frame.commands.domains("attack")[0]
        for index, actor in enumerate(frame.actors):
            if actor.id in domain:
                targets.append(_row_target(index + 1, Attack(actor.id)))
    elif isinstance(viewport, DialogueView) and "choose" in names:
        domain = frame.commands.domains("choose")[0]
        first_choice_row = len(text) - len(viewport.choices)
        for index in range(len(viewport.choices)):
            if str(index + 1) in domain:
                targets.append(
                    _row_target(first_choice_row + index, Choose(str(index + 1)))
                )
    elif isinstance(viewport, LockView) and "pick" in names:
        targets.append(_row_target(1, Pick()))
    targets.extend(_exit_slot_targets(frame))
    return tuple(targets)


def click(scene: Scene, pos: tuple[int, int]) -> Command | None:
    """The command under a click, or ``None``. Pure geometry over the Scene."""
    x, y = pos
    for target in scene.targets:
        if target.x <= x < target.x + target.w and target.y <= y < target.y + target.h:
            return target.command
    return None


def compose(
    frame: SemanticFrame, log: tuple[str, ...], *, bar: str | None = None
) -> Scene:
    """The whole window as data. Pure: same frame, log, and bar, same Scene."""
    viewport = frame.viewport
    cells: tuple[Cell, ...] = ()
    text: tuple[str, ...] = ()
    if isinstance(viewport, GridView):
        cells = _grid_cells(viewport)
    elif isinstance(viewport, RoomView):
        text = _room_text(viewport)
    elif isinstance(viewport, MenuView):
        text = _menu_text(frame)
    elif isinstance(viewport, DialogueView):
        text = _dialogue_text(viewport)
    else:
        assert isinstance(viewport, LockView)
        text = _lock_text(viewport)
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
        bar=bar,
        targets=_targets(frame, text),
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
