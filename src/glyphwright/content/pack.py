"""Content packs and their identity.

A pack hashes to a pack id that enters the run fingerprint, so any content
change invalidates recorded baselines and TermVerify can catch "test passed, but
against different data" (design 0003 section 8.2).

Slice 1 ships one built-in reference pack. TOML loading, schema validation, and
file/line diagnostics arrive with the content-driven slices; the hashing and
identity contract is established here so the fingerprint is real from day one.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from glyphwright.world.entities import Actor, Blocker, Entity, Position, Renderable
from glyphwright.world.grid import GridSpace
from glyphwright.world.space import EntityId

_REFERENCE_AREA = "village"
_REFERENCE_MAP = """\
#########
#.......#
#..##...#
#.......#
#########"""
_REFERENCE_START = (1, 1)


@dataclass(frozen=True, slots=True)
class ContentPack:
    """Validated content plus the hash that identifies it."""

    name: str
    areas: tuple[GridSpace, ...]
    entities: tuple[Entity, ...]

    @property
    def pack_id(self) -> str:
        """A stable ``name@sha256:…`` identifier over canonical content."""
        payload = json.dumps(
            {
                "name": self.name,
                "areas": [
                    {"area": space.area, "rows": list(space.rows)}
                    for space in self.areas
                ],
                "entities": [
                    {
                        "id": entity.id,
                        "at": str(entity.at()) if entity.at() else None,
                        "actor": (
                            None
                            if entity.actor is None
                            else {
                                "name": entity.actor.name,
                                "hp": entity.actor.hp,
                                "max_hp": entity.actor.max_hp,
                            }
                        ),
                        "glyph": (
                            None
                            if entity.renderable is None
                            else entity.renderable.glyph
                        ),
                        "blocker": entity.blocker is not None,
                    }
                    for entity in sorted(self.entities, key=lambda e: e.id)
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return f"{self.name}@sha256:{digest}"


def reference_pack() -> ContentPack:
    """The built-in pack the demo session and the test suite both use."""
    space = GridSpace.from_text(_REFERENCE_AREA, _REFERENCE_MAP)
    player_id: EntityId = "player"
    player = Entity(
        id=player_id,
        position=Position(at=space.pos(*_REFERENCE_START)),
        actor=Actor(name="Wren", hp=20, max_hp=20),
        blocker=Blocker(),
        renderable=Renderable(glyph="@"),
    )
    return ContentPack(name="reference-vale", areas=(space,), entities=(player,))
