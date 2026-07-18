"""Tiered grid frames: one cell names its ground, any fixture, and any actor.

The compositing tiers are a frame-model change at the source (design 0012 §4):
``GridView`` no longer collapses a cell to one glyph, so "the floor persists
under the player" is a fact the frame carries, not a frontend workaround.
Single-glyph surfaces (plain, TUI) project the tiers back with the declared
precedence actor > fixture > ground (0012 §4.1).
"""

from __future__ import annotations

from pathlib import Path

from glyphwright.api import Engine
from glyphwright.content.pack import reference_pack
from glyphwright.frames.frame import GridView, flatten
from glyphwright.kernel.commands import Move, Take


def _engine() -> Engine:
    return Engine.new(reference_pack(), seed=17)


def _viewport(engine: Engine) -> GridView:
    viewport = engine.frame().viewport
    assert isinstance(viewport, GridView)
    return viewport


def _cell(viewport: GridView, x: int, y: int) -> tuple[str, str | None, str | None]:
    row = viewport.cells[y]
    cell = row[x]
    return cell.ground, cell.fixture, cell.actor


# -- the tiered model ----------------------------------------------------------


def test_a_cell_carries_ground_fixture_and_actor() -> None:
    viewport = _viewport(_engine())
    # The player starts at (1,1), standing on the floor: all three tiers
    # are populated in one cell.
    assert _cell(viewport, 1, 1) == (".", None, "@")


def test_an_actor_on_the_map_leaves_the_ground_beneath_it() -> None:
    viewport = _viewport(_engine())
    # The goblin at (2,3) composits over the floor; before tiers the floor
    # glyph was simply overwritten.
    assert _cell(viewport, 2, 3) == (".", None, "g")


def test_an_item_is_a_fixture_over_the_ground() -> None:
    viewport = _viewport(_engine())
    assert _cell(viewport, 3, 1) == (".", "!", None)


def test_a_portal_is_a_fixture() -> None:
    viewport = _viewport(_engine())
    assert _cell(viewport, 7, 1) == (".", "+", None)


def test_a_wall_cell_has_ground_only() -> None:
    viewport = _viewport(_engine())
    assert _cell(viewport, 0, 0) == ("#", None, None)


def test_cells_are_immutable_rows() -> None:
    viewport = _viewport(_engine())
    assert isinstance(viewport.cells, tuple)
    assert all(isinstance(row, tuple) for row in viewport.cells)


# -- the declared precedence projection ----------------------------------------


def test_flatten_recovers_the_single_glyph_surface() -> None:
    viewport = _viewport(_engine())
    assert flatten(viewport)[1][1] == "@"
    assert flatten(viewport)[1][3] == "!"
    assert flatten(viewport)[3][2] == "g"
    assert flatten(viewport)[0][0] == "#"


def test_flatten_prefers_the_actor_over_a_fixture() -> None:
    engine = _engine()
    engine.step(Move("east"))
    engine.step(Move("east"))  # (3,1): onto the potion
    viewport = _viewport(engine)
    assert _cell(viewport, 3, 1) == (".", "!", "@")
    assert flatten(viewport)[1][3] == "@"


def test_flatten_prefers_a_fixture_over_the_ground() -> None:
    engine = _engine()
    engine.step(Move("east"))
    engine.step(Move("east"))
    engine.step(Take("potion-minor"))
    engine.step(Move("west"))
    engine.step(Move("west"))
    viewport = _viewport(engine)
    # Taken: no fixture anywhere; flatten falls back to bare floor.
    assert _cell(viewport, 3, 1) == (".", None, None)
    assert flatten(viewport)[1][3] == "."


# -- fog of war over tiers -----------------------------------------------------


def test_unseen_cells_are_unseen_on_every_tier(tmp_path: Path) -> None:
    from glyphwright.content.loader import load_pack

    fov_pack = {
        "pack.toml": 'name = "lantern"\n',
        "areas.toml": (
            '[[grid]]\narea = "vault"\nfov = 2\nrows = """\n'
            "#########\n"
            "#.......#\n"
            "#...#...#\n"
            "#.......#\n"
            '#########"""\n'
        ),
        "entities.toml": (
            '[[entity]]\nid = "player"\nposition = "vault:1,1"\nblocker = true\n'
            "[entity.actor]\nname = 'Lamp'\nhp = 5\nmax_hp = 5\n"
            "[entity.renderable]\nglyph = '@'\nlabel = 'player'\n"
        ),
    }
    for name, text in fov_pack.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    engine = Engine.new(load_pack(tmp_path), seed=5)
    viewport = _viewport(engine)
    assert _cell(viewport, 7, 1) == ("?", None, None)
    assert _cell(viewport, 7, 3) == ("?", None, None)
    assert flatten(viewport)[1][7] == "?"
