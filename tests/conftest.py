"""Shared test helpers."""

from __future__ import annotations

import pathlib
import tempfile

from glyphwright.content.loader import load_pack
from glyphwright.content.pack import ContentPack


def build_pack(files: dict[str, str], *, name: str = "testpack") -> ContentPack:
    """Load a throwaway TOML pack from in-memory file contents.

    The one tempdir-pack builder the suites share, so a change to pack
    loading (a new mandatory key, say) is fixed here once.
    """
    with tempfile.TemporaryDirectory() as raw:
        root = pathlib.Path(raw)
        (root / "pack.toml").write_text(f'name = "{name}"\n', encoding="utf-8")
        for filename, content in files.items():
            (root / filename).write_text(content, encoding="utf-8")
        return load_pack(root)
