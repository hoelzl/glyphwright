"""The TOML loader: shape checks, and errors located to file and line."""

from __future__ import annotations

from pathlib import Path

import pytest

from glyphwright.api import load_pack, reference_pack
from glyphwright.content.loader import PackError, header_lines, parse_pack

PACK = 'name = "reference-vale"\n'
AREAS = '''[[grid]]
area = "village"
rows = """
#########
#.......#
#..##...#
#.......#
#########"""
'''
ENTITIES = """[[entity]]
id = "player"
position = "village:1,1"
blocker = true

[entity.actor]
name = "Wren"
hp = 20
max_hp = 20

[entity.renderable]
glyph = "@"
label = "player"

[[entity]]
id = "goblin-1"
position = "village:2,3"
blocker = true

[entity.actor]
name = "Goblin"
hp = 6
max_hp = 6

[entity.renderable]
glyph = "g"
label = "goblin"
"""


def _sources(**overrides: str) -> dict[str, str]:
    sources = {"pack.toml": PACK, "areas.toml": AREAS, "entities.toml": ENTITIES}
    sources.update({name.replace("_", "."): text for name, text in overrides.items()})
    return sources


def _error(**overrides: str) -> PackError:
    with pytest.raises(PackError) as caught:
        parse_pack(_sources(**overrides))
    return caught.value


def test_a_one_area_pack_loads() -> None:
    pack = parse_pack(_sources())
    assert [space.area for space in pack.areas] == ["village"]
    assert [entity.id for entity in pack.entities] == ["player", "goblin-1"]


def test_a_syntax_error_names_file_line_and_column() -> None:
    error = _error(entities_toml=ENTITIES.replace("hp = 20", "hp = = 20"))
    assert (error.file, error.line) == ("entities.toml", 8)
    assert error.column is not None
    assert str(error).startswith("entities.toml:8:")


def test_an_unknown_key_is_reported_at_its_entity_header() -> None:
    error = _error(
        entities_toml=ENTITIES.replace(
            'id = "goblin-1"', 'id = "goblin-1"\ncolour = "green"'
        )
    )
    assert str(error) == "entities.toml:15: entity 'goblin-1': unknown key 'colour'"


def test_a_key_from_a_later_slice_says_so() -> None:
    error = _error(entities_toml=ENTITIES + "\n[entity.ai]\nhostile = true\n")
    assert (
        error.message
        == "entity 'goblin-1': 'ai' is not supported by this engine version"
    )


def test_a_later_actor_key_says_so() -> None:
    error = _error(entities_toml=ENTITIES.replace("max_hp = 6", "max_hp = 6\nmp = 3"))
    assert "'mp' is not supported" in error.message


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("abilities.toml", "this file is not supported by this engine version"),
        ("notes.toml", "unknown file in a content pack"),
    ],
)
def test_extra_files_are_refused(name: str, message: str) -> None:
    with pytest.raises(PackError) as caught:
        parse_pack(_sources() | {name: ""})
    assert (caught.value.file, caught.value.message) == (name, message)


def test_a_missing_file_is_named() -> None:
    sources = _sources()
    del sources["areas.toml"]
    with pytest.raises(PackError, match="areas.toml: file is missing"):
        parse_pack(sources)


@pytest.mark.parametrize(
    ("value", "expected"), [('"20"', "an integer"), ("true", "an integer")]
)
def test_values_are_type_checked(value: str, expected: str) -> None:
    error = _error(entities_toml=ENTITIES.replace("hp = 20", f"hp = {value}"))
    assert error.line == 1
    assert f"'hp' must be {expected}" in error.message


def test_a_duplicate_id_is_reported_where_it_repeats() -> None:
    # v0 finding L1, now located.
    error = _error(entities_toml=ENTITIES.replace('"goblin-1"', '"player"', 1))
    assert error.line == 15
    assert "is defined twice" in error.message


def test_hp_out_of_range_is_located() -> None:
    # v0 finding L2, now located.
    error = _error(entities_toml=ENTITIES.replace("\nhp = 6", "\nhp = 7"))
    assert (error.file, error.line) == ("entities.toml", 15)


def test_a_malformed_position_is_located() -> None:
    error = _error(entities_toml=ENTITIES.replace('"village:2,3"', '"village"'))
    assert error.line == 15
    assert "malformed position" in error.message


def test_a_ragged_grid_is_located_at_its_header() -> None:
    error = _error(areas_toml=AREAS.replace("#..##...#", "#..##..#"))
    assert (error.file, error.line) == ("areas.toml", 1)
    assert "equal width" in error.message


def test_a_byte_order_mark_is_accepted() -> None:
    # v2 finding N6.
    pack = parse_pack(_sources(pack_toml="﻿" + PACK))
    assert pack.name == "reference-vale"


def test_portals_are_parsed() -> None:
    door = (
        '\n[[entity]]\nid = "hole"\nposition = "village:7,3"\n'
        '\n[entity.portal]\ntoken = "down"\nto = "village:7,1"\n'
    )
    pack = parse_pack(_sources(entities_toml=ENTITIES + door))
    hole = next(entity for entity in pack.entities if entity.id == "hole")
    assert hole.portal is not None
    assert (hole.portal.token, str(hole.portal.to)) == ("down", "village:7,1")


def test_the_header_index_ignores_headers_inside_strings() -> None:
    text = (
        'note = """\n[[entity]]\n"""\n'
        '[[entity]] # a comment\nx = "[[entity]]"\n  [[ entity ]]\n'
    )
    assert header_lines(text, "entity") == [4, 6]


def test_without_a_trustworthy_index_the_line_is_left_out() -> None:
    inline = 'entity = [{ id = "player", colour = "red" }]\n'
    error = _error(entities_toml=inline)
    assert error.line is None
    assert str(error) == "entities.toml: entity 'player': unknown key 'colour'"


def test_a_missing_player_is_reported_without_a_line() -> None:
    error = _error(entities_toml=ENTITIES.replace('"player"', '"wren"'))
    assert error.line is None
    assert "'player' entity" in error.message


def _write(root: Path, sources: dict[str, str]) -> Path:
    for name, text in sources.items():
        (root / name).write_text(text, encoding="utf-8", newline="\n")
    return root


def test_load_pack_reads_a_directory(tmp_path: Path) -> None:
    loaded = load_pack(_write(tmp_path, _sources()))
    assert loaded.pack_id == parse_pack(_sources()).pack_id


def test_load_pack_ignores_files_that_are_not_toml(tmp_path: Path) -> None:
    (_write(tmp_path, _sources()) / "README.md").write_text("notes")
    assert load_pack(tmp_path).name == "reference-vale"


def test_load_pack_refuses_a_file_that_is_not_utf8(tmp_path: Path) -> None:
    _write(tmp_path, _sources())
    (tmp_path / "pack.toml").write_bytes(b'name = "caf\xe9"\n')
    with pytest.raises(PackError, match="pack.toml: not valid UTF-8"):
        load_pack(tmp_path)


def test_load_pack_refuses_a_path_that_is_not_a_directory(tmp_path: Path) -> None:
    with pytest.raises(PackError, match="is not a pack directory"):
        load_pack(tmp_path / "missing")


def test_the_reference_pack_is_loaded_from_the_package() -> None:
    assert reference_pack() is reference_pack()
    assert reference_pack().name == "reference-vale"


POTION = """
[[entity]]
id = "potion"
position = "village:3,1"

[entity.item]
name = "Potion"

[entity.consumable]
heal = 6
"""

SWORD = """
[[entity]]
id = "sword"
position = "village:6,3"

[entity.item]
name = "Sword"

[entity.equippable]
slot = "weapon"
modifiers = [{ stat = "atk", op = "add", value = 3 }]
"""


def test_items_equipment_and_stats_load() -> None:
    entities = ENTITIES.replace(
        "max_hp = 20", "max_hp = 20\nstats = { def = 3, atk = 5 }"
    )
    pack = parse_pack(_sources(entities_toml=entities + POTION + SWORD))
    by_id = {entity.id: entity for entity in pack.entities}
    assert by_id["player"].actor is not None
    assert by_id["player"].actor.base_stats == (("atk", 5), ("def", 3))
    assert by_id["potion"].consumable is not None
    assert by_id["potion"].consumable.heal == 6
    sword = by_id["sword"].equippable
    assert sword is not None
    assert (sword.slot, sword.modifiers[0].value) == ("weapon", 3)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (('op = "add"', 'op = "sub"'), "unknown modifier op 'sub'"),
        (('op = "add", value = 3', 'op = "mul", value = -10'), "value >= 0"),
        (('stat = "atk"', 'stat = "a.tk"'), "may not contain '.'"),
        (('slot = "weapon"', 'slot = "two hands"'), "whitespace-free"),
    ],
)
def test_bad_equipment_is_refused_at_its_header(
    change: tuple[str, str], message: str
) -> None:
    error = _error(entities_toml=ENTITIES + SWORD.replace(*change))
    assert error.line is not None
    assert message in error.message


def test_a_stat_must_be_an_integer() -> None:
    entities = ENTITIES.replace("max_hp = 20", 'max_hp = 20\nstats = { atk = "5" }')
    assert "stat 'atk' must be an integer" in _error(entities_toml=entities).message


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (("heal = 6", "heal = 0"), "heal at least 1 hp"),
        (("heal = 6", "heal = 6\nmana = 2"), "'mana' is not supported"),
        (('[entity.item]\nname = "Potion"\n', ""), "must be an item"),
        (('position = "village:3,1"\n', ""), "must have a position"),
        (("[entity.item]", "blocker = true\n\n[entity.item]"), "cannot be an actor"),
    ],
)
def test_bad_items_are_refused(change: tuple[str, str], message: str) -> None:
    error = _error(entities_toml=ENTITIES + POTION.replace(*change))
    assert message in error.message


@pytest.mark.parametrize("entity_id", ["world", "a.b"])
def test_ids_that_queries_could_not_reach_are_refused(entity_id: str) -> None:
    # v2 finding N8.
    error = _error(entities_toml=ENTITIES.replace('"goblin-1"', f'"{entity_id}"'))
    assert "may not contain '.' or be 'world'" in error.message
