"""The presentation manifest: load, validate, and hash it (design 0012 §5).

The manifest is content, not code, and is *not* the semantic source of truth —
it maps semantic tile/entity kinds to assets and carries decoration policy and
presentation hints. Because ``compose`` reads it, the manifest participates in
determinism: its hash joins the presentation fingerprint, so "same seed,
different manifest" is detectably a different presentation.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_a_manifest_loads_its_bindings_and_hints(tmp_path: Path) -> None:
    from glyphwright.frontends.presentation.manifest import load_manifest

    (tmp_path / "presentation.toml").write_text(
        '[bindings]\n"#" = "tiles/wall.png"\n"." = "tiles/floor.png"\n'
        "[hints]\ntile_footprint = 16\n",
        encoding="utf-8",
    )
    manifest = load_manifest(tmp_path)
    assert manifest.bindings == {"#": "tiles/wall.png", ".": "tiles/floor.png"}
    assert manifest.hints == {"tile_footprint": 16}


def test_a_manifest_is_optional_and_absent_means_empty(tmp_path: Path) -> None:
    from glyphwright.frontends.presentation.manifest import load_manifest

    manifest = load_manifest(tmp_path)
    assert manifest.bindings == {}
    assert manifest.hints == {}


def test_the_hash_is_stable_for_identical_content(tmp_path: Path) -> None:
    from glyphwright.frontends.presentation.manifest import load_manifest

    text = '[bindings]\n"@" = "tiles/player.png"\n'
    (tmp_path / "presentation.toml").write_text(text, encoding="utf-8")
    first = load_manifest(tmp_path).hash
    second = load_manifest(tmp_path).hash
    assert first == second and first.startswith("sha256:")


def test_different_content_yields_a_different_hash(tmp_path: Path) -> None:
    from glyphwright.frontends.presentation.manifest import load_manifest

    (tmp_path / "presentation.toml").write_text(
        '[bindings]\n"@" = "tiles/a.png"\n', encoding="utf-8"
    )
    one = load_manifest(tmp_path).hash
    (tmp_path / "presentation.toml").write_text(
        '[bindings]\n"@" = "tiles/b.png"\n', encoding="utf-8"
    )
    other = load_manifest(tmp_path).hash
    assert one != other


def test_a_non_string_binding_is_a_located_error(tmp_path: Path) -> None:
    from glyphwright.frontends.presentation.manifest import (
        ManifestError,
        load_manifest,
    )

    (tmp_path / "presentation.toml").write_text(
        '[bindings]\n"#" = 3\n', encoding="utf-8"
    )
    with pytest.raises(ManifestError, match="presentation.toml"):
        load_manifest(tmp_path)


def test_a_non_single_glyph_binding_key_is_refused(tmp_path: Path) -> None:
    from glyphwright.frontends.presentation.manifest import (
        ManifestError,
        load_manifest,
    )

    (tmp_path / "presentation.toml").write_text(
        '[bindings]\n"wall" = "tiles/wall.png"\n', encoding="utf-8"
    )
    with pytest.raises(ManifestError, match="single glyph"):
        load_manifest(tmp_path)


def test_an_unknown_top_level_key_is_refused(tmp_path: Path) -> None:
    from glyphwright.frontends.presentation.manifest import (
        ManifestError,
        load_manifest,
    )

    (tmp_path / "presentation.toml").write_text("[surprise]\nx = 1\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="unknown"):
        load_manifest(tmp_path)
