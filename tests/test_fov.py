"""Field of view: a pack-level option and a pure view filter (design 0006 §1).

No state, no events: the fold, replay, and grammars are untouched by
construction, and these tests pin exactly that.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from glyphwright.api import Engine
from glyphwright.content.loader import PackError, load_pack
from glyphwright.frames.frame import GridView
from glyphwright.kernel.commands import Move
from glyphwright.world.grid import GridSpace

_FOV_PACK = {
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
        '[[entity]]\nid = "lurker"\nposition = "vault:7,3"\nblocker = true\n'
        "[entity.actor]\nname = 'Lurker'\nhp = 5\nmax_hp = 5\n"
        "[entity.renderable]\nglyph = 'L'\nlabel = 'lurker'\n"
        "[entity.ai]\nhostile = true\n"
    ),
}


def _engine(tmp_path: Path) -> Engine:
    for name, text in _FOV_PACK.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    return Engine.new(load_pack(tmp_path), seed=5)


def _tiles(engine: Engine) -> tuple[str, ...]:
    viewport = engine.frame().viewport
    assert isinstance(viewport, GridView)
    return viewport.tiles


def test_far_tiles_are_unseen(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    tiles = _tiles(engine)
    assert tiles[1][1] == "@"
    assert tiles[1][2] == "."  # within radius 2
    assert tiles[1][7] == "?"  # far beyond the lantern
    assert tiles[3][7] == "?"


def test_walls_are_visible_but_opaque(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    engine.step(Move("east"))
    engine.step(Move("east"))
    engine.step(Move("south"))  # (3,2), beside the pillar at (4,2)
    tiles = _tiles(engine)
    assert tiles[2][4] == "#", "the wall itself is visible"
    assert tiles[2][5] == "?", "what lies behind the wall is not"


def test_unseen_actors_are_neither_drawn_nor_summarised(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    tiles = _tiles(engine)
    assert not any("L" in row for row in tiles), "the lurker is beyond the light"
    assert {actor.id for actor in engine.frame().actors} == {"player"}


def test_visible_actors_appear_when_reached(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    for _ in range(5):
        engine.step(Move("east"))
    engine.step(Move("south"))
    engine.step(Move("south"))  # (6,3), one tile from the lurker at (7,3)
    tiles = _tiles(engine)
    assert any("L" in row for row in tiles)
    assert {actor.id for actor in engine.frame().actors} == {"player", "lurker"}


def test_the_unseen_glyph_is_in_the_legend(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    viewport = engine.frame().viewport
    assert isinstance(viewport, GridView)
    assert ("?", "unseen") in viewport.legend


def test_fov_frames_round_trip_in_plain(tmp_path: Path) -> None:
    from glyphwright.frontends import plain

    engine = _engine(tmp_path)
    frame = engine.frame()
    assert plain.parse(plain.render(frame)) == plain.project(frame)


def test_fov_changes_no_events_and_no_state(tmp_path: Path) -> None:
    """Visibility is a view concern: steps produce the same events with or
    without the lantern, and nothing about FOV enters the fold."""
    for name, text in _FOV_PACK.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    lit = Engine.new(load_pack(tmp_path), seed=9)
    (tmp_path / "areas.toml").write_text(
        _FOV_PACK["areas.toml"].replace("fov = 2\n", ""), encoding="utf-8"
    )
    omniscient = Engine.new(load_pack(tmp_path), seed=9)
    for token in ("east", "east", "south", "east"):
        assert lit.step(Move(token)).events == omniscient.step(Move(token)).events


def test_observe_filters_the_same_way(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    state = engine._state
    space = state.areas["vault"]
    assert isinstance(space, GridSpace)
    observation = space.observe(state, "player")
    assert all(position in observation.visible for position in [space.pos(1, 1)])
    assert space.pos(7, 3) not in observation.visible
    assert observation.actors == ()


def test_omniscient_areas_are_unchanged(tmp_path: Path) -> None:
    from glyphwright.content.pack import reference_pack

    engine = Engine.new(reference_pack(), seed=1)
    tiles = _tiles(engine)
    assert not any("?" in row for row in tiles)


def test_fov_on_a_room_area_is_a_load_error(tmp_path: Path) -> None:
    for name, text in _FOV_PACK.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    (tmp_path / "areas.toml").write_text(
        _FOV_PACK["areas.toml"] + '\n[[rooms]]\narea = "attic"\nfov = 1\n'
        '[[rooms.room]]\nid = "a"\nname = "A"\ndescription = "Dust."\n',
        encoding="utf-8",
    )
    with pytest.raises(PackError, match="fov"):
        load_pack(tmp_path)


def test_a_non_positive_radius_is_a_load_error(tmp_path: Path) -> None:
    for name, text in _FOV_PACK.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    (tmp_path / "areas.toml").write_text(
        _FOV_PACK["areas.toml"].replace("fov = 2", "fov = 0"), encoding="utf-8"
    )
    with pytest.raises(PackError, match="fov"):
        load_pack(tmp_path)
