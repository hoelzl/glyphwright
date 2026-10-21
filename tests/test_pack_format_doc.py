"""The authoring reference lists every key the loader accepts.

The reference is hand-written; this test is what keeps it from drifting.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from glyphwright.content import loader

REFERENCE = (
    Path(__file__).resolve().parents[1] / "docs" / "authoring" / "pack-format.md"
)

_SPECS = (
    loader.PACK_SPEC,
    loader.GRID_SPEC,
    loader.ENTITY_SPEC,
    loader.ACTOR_SPEC,
    loader.RENDERABLE_SPEC,
    loader.PORTAL_SPEC,
)
_ACCEPTED = sorted({key for spec in _SPECS for key in spec})
_LATER = sorted(
    loader._LATER_FILES
    | loader._LATER_AREA_SECTIONS
    | loader._LATER_GRID_KEYS
    | loader._LATER_COMPONENTS
    | loader._LATER_ACTOR_KEYS
)


@pytest.mark.parametrize("key", _ACCEPTED)
def test_every_accepted_key_is_documented(key: str) -> None:
    assert f"`{key}`" in REFERENCE.read_text(encoding="utf-8"), (
        f"add {key!r} to {REFERENCE.name}"
    )


@pytest.mark.parametrize("name", _LATER)
def test_every_unsupported_part_is_listed(name: str) -> None:
    assert f"`{name}`" in REFERENCE.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", loader.REQUIRED_FILES)
def test_every_file_is_documented(name: str) -> None:
    assert f"`{name}`" in REFERENCE.read_text(encoding="utf-8")
