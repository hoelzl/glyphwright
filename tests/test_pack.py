"""Content packs: load-time validation and content identity."""

from __future__ import annotations

import dataclasses

import pytest

from glyphwright.api import reference_pack
from glyphwright.content.pack import ContentPack
from glyphwright.world.entities import Actor, Ai, Entity, Position
from glyphwright.world.space import PosId


def _with_entities(*entities: Entity) -> ContentPack:
    pack = reference_pack()
    return ContentPack(
        name=pack.name, areas=pack.areas, entities=(*pack.entities, *entities)
    )


def _goblin(**changes: object) -> Entity:
    goblin = next(e for e in reference_pack().entities if e.id == "goblin-1")
    return dataclasses.replace(goblin, **changes)  # type: ignore[arg-type]


def test_the_reference_pack_loads() -> None:
    pack = reference_pack()
    assert [space.area for space in pack.areas] == ["village", "warren"]
    assert {entity.id for entity in pack.entities} >= {"player", "warren-hole"}


def test_a_duplicate_entity_id_is_rejected() -> None:
    # v0 finding L1.
    with pytest.raises(ValueError, match="goblin-1.*defined twice"):
        _with_entities(_goblin())


@pytest.mark.parametrize(("hp", "max_hp"), [(-1, 6), (7, 6)])
def test_hp_outside_its_bounds_is_rejected(hp: int, max_hp: int) -> None:
    # v0 finding L2.
    actor = Actor(name="Odd", hp=hp, max_hp=max_hp)
    with pytest.raises(ValueError, match="outside"):
        _with_entities(_goblin(id="odd-1", actor=actor))


def test_an_id_with_whitespace_is_rejected() -> None:
    with pytest.raises(ValueError, match="whitespace-free"):
        _with_entities(_goblin(id="two words"))


def test_an_entity_off_the_map_is_rejected() -> None:
    village = reference_pack().areas[0]
    with pytest.raises(ValueError, match="off the map"):
        _with_entities(_goblin(id="lost-1", position=Position(at=village.pos(99, 0))))


def test_a_pack_needs_a_placed_player() -> None:
    pack = reference_pack()
    without_player = tuple(e for e in pack.entities if e.id != "player")
    with pytest.raises(ValueError, match="'player'"):
        ContentPack(name=pack.name, areas=pack.areas, entities=without_player)


def test_the_pack_id_is_stable_and_order_independent() -> None:
    pack = reference_pack()
    reordered = ContentPack(
        name=pack.name, areas=pack.areas, entities=tuple(reversed(pack.entities))
    )
    assert pack.pack_id == reordered.pack_id == reference_pack().pack_id
    assert pack.pack_id.startswith("reference-vale@sha256:")


def test_any_content_change_changes_the_pack_id() -> None:
    changed = _with_entities(_goblin(id="goblin-2", position=None, ai=None))
    assert changed.pack_id != reference_pack().pack_id


FREE_TILE = Position(at=PosId.parse("village:5,1"))


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"ai": Ai(hostile=False)}, "only hostile ai is supported by this engine"),
        ({"actor": None}, "an ai must be a placed actor"),
    ],
)
def test_ai_rules(changes: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _with_entities(_goblin(id="goblin-2", position=FREE_TILE, **changes))


def test_the_player_cannot_have_an_ai() -> None:
    pack = reference_pack()
    entities = tuple(
        dataclasses.replace(e, ai=Ai()) if e.id == "player" else e
        for e in pack.entities
    )
    with pytest.raises(ValueError, match="the player cannot have an ai"):
        ContentPack(name=pack.name, areas=pack.areas, entities=entities)
