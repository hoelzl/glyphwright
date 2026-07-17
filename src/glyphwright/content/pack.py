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
from dataclasses import asdict, dataclass

from glyphwright.world.entities import (
    Actor,
    AiBehavior,
    Blocker,
    Consumable,
    Entity,
    Equippable,
    Item,
    Position,
    Renderable,
    StatModifier,
)
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
_REFERENCE_POTION_AT = (3, 1)
_REFERENCE_SWORD_AT = (6, 3)
_REFERENCE_GOBLIN_AT = (2, 3)


@dataclass(frozen=True, slots=True)
class ContentPack:
    """Validated content plus the hash that identifies it."""

    name: str
    areas: tuple[GridSpace, ...]
    entities: tuple[Entity, ...]

    @property
    def pack_id(self) -> str:
        """A stable ``name@sha256:…`` identifier over canonical content.

        Hashing walks every component field via ``asdict``, so adding a
        component automatically widens the identity — a pack cannot change
        content without changing its id.
        """
        payload = json.dumps(
            {
                "name": self.name,
                "areas": [
                    {"area": space.area, "rows": list(space.rows)}
                    for space in self.areas
                ],
                "entities": [
                    asdict(entity)
                    for entity in sorted(self.entities, key=lambda e: e.id)
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return f"{self.name}@sha256:{digest}"


def reference_pack() -> ContentPack:
    """The built-in pack the demo session and the test suite both use.

    The player starts wounded (17/20, matching the design's transcripts) so the
    healing potion has something observable to do.
    """
    space = GridSpace.from_text(_REFERENCE_AREA, _REFERENCE_MAP)
    player_id: EntityId = "player"
    player = Entity(
        id=player_id,
        position=Position(at=space.pos(*_REFERENCE_START)),
        actor=Actor(
            name="Wren",
            hp=17,
            max_hp=20,
            base_stats=(("atk", 5), ("def", 3)),
        ),
        blocker=Blocker(),
        renderable=Renderable(glyph="@"),
    )
    potion = Entity(
        id="potion-minor",
        position=Position(at=space.pos(*_REFERENCE_POTION_AT)),
        item=Item(name="Minor Potion"),
        consumable=Consumable(heal=6),
        renderable=Renderable(glyph="!"),
    )
    sword = Entity(
        id="iron-sword",
        position=Position(at=space.pos(*_REFERENCE_SWORD_AT)),
        item=Item(name="Iron Sword"),
        equippable=Equippable(
            slot="weapon",
            modifiers=(StatModifier(stat="atk", op="add", value=3),),
        ),
        renderable=Renderable(glyph="/"),
    )
    goblin = Entity(
        id="goblin-1",
        position=Position(at=space.pos(*_REFERENCE_GOBLIN_AT)),
        actor=Actor(
            name="Goblin",
            hp=6,
            max_hp=6,
            base_stats=(("atk", 3), ("def", 1)),
        ),
        blocker=Blocker(),
        renderable=Renderable(glyph="g"),
        ai=AiBehavior(hostile=True),
    )
    return ContentPack(
        name="reference-vale", areas=(space,), entities=(player, potion, sword, goblin)
    )
