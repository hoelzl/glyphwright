"""Portals join grid areas, and load-time rules keep content playable."""

from __future__ import annotations

import pytest

from glyphwright.content.pack import ContentError, ContentPack
from glyphwright.kernel.commands import Move
from glyphwright.kernel.rng import Rng
from glyphwright.kernel.state import MODE_EXPLORATION, PLAYER, WorldState
from glyphwright.kernel.step import step
from glyphwright.modes import exploration
from glyphwright.world.entities import (
    Actor,
    Blocker,
    Entity,
    Portal,
    Position,
    Renderable,
)
from glyphwright.world.grid import GridSpace
from glyphwright.world.space import PosId

HALL = GridSpace.from_text("hall", "#####\n#...#\n#####")
CELLAR = GridSpace.from_text("cellar", "####\n#..#\n####")
DOOR_AT = HALL.pos(3, 1)
CELLAR_FLOOR = CELLAR.pos(1, 1)


def _player() -> Entity:
    return Entity(
        id=PLAYER,
        position=Position(at=HALL.pos(1, 1)),
        actor=Actor(name="Wren", hp=5, max_hp=5),
        blocker=Blocker(),
        renderable=Renderable(glyph="@", label="player"),
    )


def _door(
    entity_id: str = "trapdoor",
    at: PosId = DOOR_AT,
    token: str = "down",
    to: PosId = CELLAR_FLOOR,
) -> Entity:
    return Entity(
        id=entity_id,
        position=Position(at=at),
        renderable=Renderable(glyph="O", label="portal"),
        portal=Portal(token=token, to=to),
    )


def _pack(*extra: Entity) -> ContentPack:
    return ContentPack(
        name="two-rooms", areas=(HALL, CELLAR), entities=(_player(), _door(), *extra)
    )


def _state(pack: ContentPack) -> WorldState:
    return WorldState(
        entities={entity.id: entity for entity in pack.entities},
        areas={space.area: space for space in pack.areas},
        mode_stack=(MODE_EXPLORATION,),
        turn=0,
        rng=Rng.from_seed(1),
    )


def test_a_portal_adds_its_token_to_the_exits_where_it_stands() -> None:
    state = _state(_pack())
    assert state.exits_from(HALL.pos(3, 1))["down"] == CELLAR.pos(1, 1)
    assert "down" not in state.exits_from(HALL.pos(2, 1))


def test_walking_through_a_portal_changes_the_area() -> None:
    state = _state(_pack())
    for _ in range(2):
        state, _ = step(state, Move("east"), state.rng)
    assert "down" in exploration.available_commands(state).domains("move")[0]
    state, events = step(state, Move("down"), state.rng)
    assert state.entity(PLAYER).at() == CELLAR.pos(1, 1)
    frame = exploration.view(state, events)
    assert frame.viewport.area == "cellar"
    assert frame.messages == ("You go down.",)


def test_a_portal_token_may_not_shadow_a_geometric_exit() -> None:
    # v0 finding K10.
    with pytest.raises(ContentError, match="shadows a geometric exit"):
        ContentPack(
            name="bad", areas=(HALL, CELLAR), entities=(_player(), _door(token="east"))
        )


def test_two_portals_on_one_tile_may_not_share_a_token() -> None:
    with pytest.raises(ContentError, match="already claims"):
        _pack(_door("hatch"))


@pytest.mark.parametrize(
    ("to", "message"),
    [(PosId("attic", "1,1"), "leads nowhere"), (CELLAR.pos(0, 0), "into a wall")],
)
def test_a_portal_must_lead_to_a_floor_tile(to: PosId, message: str) -> None:
    with pytest.raises(ContentError, match=message):
        ContentPack(
            name="bad", areas=(HALL, CELLAR), entities=(_player(), _door(to=to))
        )


def test_a_portal_cannot_be_an_actor() -> None:
    walking = Entity(
        id="mimic",
        position=Position(at=HALL.pos(2, 1)),
        actor=Actor(name="Mimic", hp=1, max_hp=1),
        portal=Portal(token="in", to=CELLAR.pos(1, 1)),
    )
    with pytest.raises(ContentError, match="actor or a blocker"):
        _pack(walking)


@pytest.mark.parametrize("local", [" 1,1", "01,1", "1_0,1", "1, 1"])
def test_only_the_canonical_position_spelling_is_on_the_map(local: str) -> None:
    # v2 finding N1: these parse to real coordinates but match no tile.
    assert not HALL.contains(PosId("hall", local))
    stray = Entity(id="stray", position=Position(at=PosId("hall", local)))
    with pytest.raises(ContentError, match="off the map"):
        _pack(stray)


@pytest.mark.parametrize("name", ["two words", "a:b"])
def test_an_area_name_must_be_one_word_without_a_colon(name: str) -> None:
    # v2 finding N2.
    odd = GridSpace(_area=name, rows=("..",))
    with pytest.raises(ContentError) as error:
        ContentPack(name="bad", areas=(HALL, odd), entities=(_player(),))
    assert error.value.subject == ("area", name)


@pytest.mark.parametrize("glyph", ["", "@@", " ", ".", "#"])
def test_a_glyph_is_one_visible_non_terrain_character(glyph: str) -> None:
    odd = Entity(
        id="odd",
        position=Position(at=HALL.pos(2, 1)),
        renderable=Renderable(glyph=glyph, label="odd"),
    )
    with pytest.raises(ContentError, match="glyph"):
        _pack(odd)


def test_one_glyph_cannot_carry_two_labels() -> None:
    # v2 finding N3: the legend would silently lose one of them.
    twin = Entity(
        id="twin",
        position=Position(at=HALL.pos(2, 1)),
        renderable=Renderable(glyph="O", label="well"),
    )
    with pytest.raises(ContentError, match="already means 'portal'"):
        _pack(twin)


def test_nothing_may_stand_in_a_wall() -> None:
    # v2 finding N4.
    buried = Entity(id="buried", position=Position(at=HALL.pos(0, 0)))
    with pytest.raises(ContentError, match="stands in a wall"):
        _pack(buried)


def test_two_blockers_may_not_share_a_tile() -> None:
    # v2 finding N5.
    crowd = Entity(id="crowd", position=Position(at=HALL.pos(1, 1)), blocker=Blocker())
    with pytest.raises(ContentError, match="already blocked by 'player'") as error:
        _pack(crowd)
    assert error.value.subject == ("entity", "crowd")
