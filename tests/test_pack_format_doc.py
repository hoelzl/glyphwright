"""The authoring reference lists every key the loader accepts.

The reference is hand-written; this test is what keeps it from drifting. A key
counts as documented only in the supported part of the page, so a key that a
slice starts accepting cannot hide in the "Not supported yet" list.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from glyphwright.content import loader

REFERENCE = (
    Path(__file__).resolve().parents[1] / "docs" / "authoring" / "pack-format.md"
)
_LATER_HEADING = "## Not supported yet"

_SPECS = (
    loader.PACK_SPEC,
    loader.GRID_SPEC,
    loader.ENTITY_SPEC,
    loader.ACTOR_SPEC,
    loader.RENDERABLE_SPEC,
    loader.PORTAL_SPEC,
    loader.ITEM_SPEC,
    loader.CONSUMABLE_SPEC,
    loader.EQUIPPABLE_SPEC,
    loader.MODIFIER_SPEC,
)
_ACCEPTED = sorted({key for spec in _SPECS for key in spec})
_LATER = sorted(
    loader._LATER_FILES
    | loader._LATER_AREA_SECTIONS
    | loader._LATER_GRID_KEYS
    | loader._LATER_COMPONENTS
    | loader._LATER_ACTOR_KEYS
    | loader._LATER_CONSUMABLE_KEYS
)


def _parts() -> tuple[str, str]:
    supported, _, later = REFERENCE.read_text(encoding="utf-8").partition(
        _LATER_HEADING
    )
    return supported, later


@pytest.mark.parametrize("key", _ACCEPTED)
def test_every_accepted_key_is_documented(key: str) -> None:
    assert f"`{key}`" in _parts()[0], f"add {key!r} to {REFERENCE.name}"


@pytest.mark.parametrize("name", _LATER)
def test_every_unsupported_part_is_listed(name: str) -> None:
    assert f"`{name}`" in _parts()[1]


@pytest.mark.parametrize("key", _ACCEPTED)
def test_no_accepted_key_is_listed_as_unsupported(key: str) -> None:
    later = _parts()[1]
    assert f"`{key}`" not in later or key in _LATER, (
        f"{key!r} is accepted now; remove it from '{_LATER_HEADING}'"
    )


@pytest.mark.parametrize("name", loader.REQUIRED_FILES)
def test_every_file_is_documented(name: str) -> None:
    assert f"`{name}`" in _parts()[0]
