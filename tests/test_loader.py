"""The TOML pack loader: located diagnostics, and the reference pack itself
as its permanent workout (design 0005)."""

from __future__ import annotations

from pathlib import Path

import pytest

from glyphwright.api import Engine
from glyphwright.content.loader import PackError, load_pack
from glyphwright.content.pack import reference_pack
from glyphwright.kernel.commands import Move

_MINIMAL = {
    "pack.toml": 'name = "closet"\n',
    "areas.toml": '[[grid]]\narea = "closet"\nrows = """\n...\n"""\n',
    "entities.toml": (
        '[[entity]]\nid = "player"\nposition = "closet:0,0"\nblocker = true\n'
        "[entity.actor]\nname = 'Mote'\nhp = 5\nmax_hp = 5\n"
    ),
}


def _write_pack(root: Path, overrides: dict[str, str] | None = None) -> Path:
    files = {**_MINIMAL, **(overrides or {})}
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")
    return root


def test_the_reference_pack_loads_from_its_toml() -> None:
    pack = reference_pack()
    assert pack.name == "reference-vale"
    assert {e.id for e in pack.entities} >= {"player", "goblin-1", "strongbox"}
    assert {a.id for a in pack.abilities} == {"firebolt", "guard"}


def test_a_minimal_external_pack_loads_and_plays(tmp_path: Path) -> None:
    pack = load_pack(_write_pack(tmp_path))
    engine = Engine.new(pack, seed=1)
    result = engine.step(Move("east"))
    assert result.accepted
    assert engine.frame().viewport.area == "closet"


def test_loading_is_deterministic(tmp_path: Path) -> None:
    root = _write_pack(tmp_path)
    assert load_pack(root).pack_id == load_pack(root).pack_id


def test_a_missing_required_file_names_itself(tmp_path: Path) -> None:
    root = _write_pack(tmp_path)
    (root / "areas.toml").unlink()
    with pytest.raises(PackError, match="areas.toml"):
        load_pack(root)


def test_a_syntax_error_carries_file_and_line(tmp_path: Path) -> None:
    root = _write_pack(tmp_path, {"areas.toml": "[[grid]\narea = 3\n"})
    with pytest.raises(PackError, match=r"areas\.toml.*line 1"):
        load_pack(root)


def test_an_unknown_key_names_its_object(tmp_path: Path) -> None:
    root = _write_pack(
        tmp_path,
        {
            "entities.toml": _MINIMAL["entities.toml"]
            + '[[entity]]\nid = "chair"\nwobbly = true\n'
        },
    )
    with pytest.raises(PackError, match=r"entities\.toml: entity 'chair'.*wobbly"):
        load_pack(root)


def test_a_semantic_error_names_its_object(tmp_path: Path) -> None:
    root = _write_pack(
        tmp_path,
        {
            "entities.toml": _MINIMAL["entities.toml"]
            + (
                '[[entity]]\nid = "hole"\nposition = "closet:1,0"\n'
                '[entity.portal]\ntoken = "down"\nto = "abyss:0,0"\n'
            )
        },
    )
    with pytest.raises(PackError, match="leads nowhere"):
        load_pack(root)


def test_an_unreachable_farewell_is_located(tmp_path: Path) -> None:
    root = _write_pack(
        tmp_path,
        {
            "entities.toml": _MINIMAL["entities.toml"]
            + (
                '[[entity]]\nid = "bore"\nposition = "closet:2,0"\n'
                "[entity.actor]\nname = 'Bore'\nhp = 1\nmax_hp = 1\n"
                '[entity.dialogue]\nroot = "loop"\n'
                '[[entity.dialogue.node]]\nid = "loop"\nline = "..."\n'
                '[[entity.dialogue.node.choice]]\ntext = "again"\nnext = "loop"\n'
            )
        },
    )
    with pytest.raises(PackError, match=r"entity 'bore'.*farewell"):
        load_pack(root)


def test_bad_ability_params_are_located(tmp_path: Path) -> None:
    root = _write_pack(
        tmp_path,
        {
            "abilities.toml": (
                '[[ability]]\nid = "zap"\nname = "Zap"\ntargeting = "self"\n'
                'effects = [{ primitive = "deal_damage", amount = "lots" }]\n'
            )
        },
    )
    with pytest.raises(PackError, match=r"ability 'zap'.*amount"):
        load_pack(root)


def test_pack_level_reference_errors_are_prefixed(tmp_path: Path) -> None:
    root = _write_pack(
        tmp_path,
        {
            "entities.toml": _MINIMAL["entities.toml"]
            + (
                '[[entity]]\nid = "box"\nposition = "closet:1,0"\n'
                '[entity.openable]\ncontains = "no-such-loot"\n'
            )
        },
    )
    with pytest.raises(PackError, match=r"pack 'closet'.*unknown entity"):
        load_pack(root)
