"""The GUI's scene layer: ``compose`` is a pure function of the frame, and the
Scene — not the pixels — is the evidence (design 0011 §3, §5).

Nothing here imports pygame: scene composition must stay verifiable with the
``gui`` extra absent, which is what the bare CI job proves.
"""

from __future__ import annotations

from glyphwright.api import Engine
from glyphwright.content.pack import reference_pack
from glyphwright.frames.frame import GridView
from glyphwright.frontends import plain
from glyphwright.frontends.gui import scene
from glyphwright.kernel.commands import Move


def _engine() -> Engine:
    return Engine.new(reference_pack(), seed=17)


def _rows(composed: scene.Scene) -> list[str]:
    """Reassemble the cell grid into glyph rows for comparison with tiles."""
    if not composed.cells:
        return []
    height = max(cell.y for cell in composed.cells) + 1
    width = max(cell.x for cell in composed.cells) + 1
    grid = [[" "] * width for _ in range(height)]
    for cell in composed.cells:
        grid[cell.y][cell.x] = cell.glyph
    return ["".join(row).rstrip() for row in grid]


# -- purity and determinism ---------------------------------------------------


def test_compose_is_pure_and_deterministic() -> None:
    frame = _engine().frame()
    log = ("You wake.",)
    assert scene.compose(frame, log) == scene.compose(frame, log)


# -- grid frames --------------------------------------------------------------


def test_grid_frames_compose_to_cells_matching_the_tiles() -> None:
    engine = _engine()
    frame = engine.step(Move("east")).frame
    composed = scene.compose(frame, frame.messages)
    assert isinstance(frame.viewport, GridView)
    assert _rows(composed) == [row.rstrip() for row in frame.viewport.tiles]
    assert composed.text == ()


def test_every_cell_carries_a_palette_color() -> None:
    frame = _engine().frame()
    composed = scene.compose(frame, ())
    for cell in composed.cells:
        assert len(cell.fg) == 3
        assert all(0 <= channel <= 255 for channel in cell.fg)
    player = [cell for cell in composed.cells if cell.glyph == "@"]
    wall = [cell for cell in composed.cells if cell.glyph == "#"]
    assert player and wall
    assert player[0].fg != wall[0].fg, "the player must stand out from walls"


# -- room frames --------------------------------------------------------------


def test_room_frames_compose_to_prose() -> None:
    engine = _engine()
    for _ in range(6):
        engine.step(Move("east"))
    frame = engine.step(Move("enter")).frame
    composed = scene.compose(frame, ())
    assert composed.cells == ()
    assert any("The Gilded Tankard" in line for line in composed.text)
    assert composed.exits, "a room's exits must stay actionable"


# -- placeholders (13A: battle/dialogue/lock defer to the terminal) -----------


def test_battle_frames_compose_to_an_honest_placeholder() -> None:
    engine = _engine()
    frame = engine.step(Move("south")).frame  # the bandit engages
    composed = scene.compose(frame, frame.messages)
    assert composed.mode == "battle"
    assert any("battle" in line for line in composed.text)
    assert any("--frontend tui" in line for line in composed.text), (
        "the placeholder must direct the player to a frontend that plays it"
    )


# -- projection consistency against plain (0011 §5.2) -------------------------


def test_the_scene_shows_everything_plain_commits_to_for_covered_views() -> None:
    engine = _engine()
    frames = [engine.frame()]
    for token in ("east", "east", "west"):
        frames.append(engine.step(Move(token)).frame)
    for _ in range(6):
        engine.step(Move("east"))
    frames.append(engine.step(Move("enter")).frame)  # a room frame

    for frame in frames:
        projection = plain.project(frame)
        composed = scene.compose(frame, frame.messages)
        assert composed.turn == projection.turn
        assert composed.mode == projection.mode
        assert composed.area == projection.area
        rows = _rows(composed)
        for tile_row in projection.tiles:
            assert tile_row.rstrip() in rows
        for message in projection.messages:
            assert message in composed.log
        # Compose wraps prose at TEXT_COLS; rejoining the wrapped lines must
        # give back every fact plain commits to, with nothing dropped.
        rejoined = " ".join(composed.text)
        for prose in projection.room:
            assert prose in rejoined
        if projection.hp is not None:
            assert f"hp {projection.hp[0]}/{projection.hp[1]}" in composed.status
        if projection.mp is not None:
            assert f"mp {projection.mp[0]}/{projection.mp[1]}" in composed.status


# -- the golden serialization -------------------------------------------------


def test_scene_text_is_deterministic_and_names_the_regions() -> None:
    engine = _engine()
    frame = engine.step(Move("east")).frame
    composed = scene.compose(frame, frame.messages)
    dump = scene.scene_text(composed)
    assert dump == scene.scene_text(scene.compose(frame, frame.messages))
    assert "turn 1" in dump
    assert "village" in dump
