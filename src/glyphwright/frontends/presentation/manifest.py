"""The presentation manifest: content that maps semantics to assets (0012 §5).

The manifest is *not* the semantic source of truth — the pack is. It carries
three things the engine does not know: which asset stands for a semantic glyph
(``[bindings]``), a seeded decoration policy (``[decoration]``, derived
material that is never kernel state), and presentation hints (``[hints]``,
such as a tile footprint). It is TOML, version-controlled, and lives beside the
content pack as ``presentation.toml``.

Because ``compose`` reads the manifest, the manifest participates in
determinism: :attr:`PresentationManifest.hash` joins the presentation
fingerprint, so "same seed, different manifest" is detectably a different
presentation — the presentation-side analogue of the pack-ID rule (0003 §8.2).
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass
from importlib.resources.abc import Traversable

_FILE = "presentation.toml"


class ManifestError(ValueError):
    """A manifest problem, located: the file and what went wrong."""


def _fail(problem: str) -> ManifestError:
    return ManifestError(f"{_FILE}: {problem}")


@dataclass(frozen=True, slots=True)
class PresentationManifest:
    """Validated presentation content plus the hash that identifies it."""

    bindings: dict[str, str]
    decoration: dict[str, object]
    hints: dict[str, object]

    @property
    def hash(self) -> str:
        """A stable ``sha256:…`` over the canonical manifest content.

        Hashing the parsed-and-validated mapping (not the raw text) means a
        cosmetic reformatting or key reordering of the TOML does not
        invalidate recorded presentations — only a real content change does.
        """
        payload = json.dumps(
            {
                "bindings": self.bindings,
                "decoration": self.decoration,
                "hints": self.hints,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_manifest(root: Traversable) -> PresentationManifest:
    """Load ``presentation.toml`` from a pack root; empty when absent.

    An absent manifest is a valid, empty presentation — the fallback of
    drawing plain glyphs needs no assets. A *present* manifest is validated:
    bindings map single glyphs to asset paths, and unknown top-level tables
    are refused so a mistyped section is a diagnostic, not silent dead config.
    """
    resource = root / _FILE
    if not resource.is_file():
        return PresentationManifest(bindings={}, decoration={}, hints={})
    try:
        text = resource.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as error:
        raise _fail(f"cannot read ({error})") from error
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise _fail(str(error)) from error

    allowed = {"bindings", "decoration", "hints"}
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise _fail(f"unknown top-level tables: {', '.join(unknown)}")

    bindings = _bindings(data.get("bindings", {}))
    decoration = _mapping("decoration", data.get("decoration", {}))
    hints = _mapping("hints", data.get("hints", {}))
    return PresentationManifest(bindings=bindings, decoration=decoration, hints=hints)


def _bindings(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise _fail("[bindings] must be a table")
    out: dict[str, str] = {}
    for glyph, asset in value.items():
        if len(glyph) != 1:
            raise _fail(f"[bindings] key {glyph!r} is not a single glyph")
        if not isinstance(asset, str):
            raise _fail(f"[bindings] {glyph!r} must name an asset path, got {asset!r}")
        out[glyph] = asset
    return out


def _mapping(section: str, value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _fail(f"[{section}] must be a table")
    return dict(value)
