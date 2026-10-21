"""The built-in reference pack: one small village, built in code.

The same village opens v0's reference world. S2 replaces this builder with a
packaged TOML pack loaded through the content loader.
"""

from __future__ import annotations

from glyphwright.content.pack import ContentPack
from glyphwright.kernel.state import PLAYER
from glyphwright.world.entities import Actor, Blocker, Entity, Position, Renderable
from glyphwright.world.grid import GridSpace

_VILLAGE = """\
#########
#.......#
#..##...#
#.......#
#########"""


def reference_pack() -> ContentPack:
    """The pack the demo session and the test suite both use."""
    village = GridSpace.from_text("village", _VILLAGE)
    player = Entity(
        id=PLAYER,
        position=Position(at=village.pos(1, 1)),
        actor=Actor(name="Wren", hp=20, max_hp=20),
        blocker=Blocker(),
        renderable=Renderable(glyph="@", label="player"),
    )
    # Inert until battle arrives in S4: it blocks a tile and shows in frames.
    goblin = Entity(
        id="goblin-1",
        position=Position(at=village.pos(2, 3)),
        actor=Actor(name="Goblin", hp=6, max_hp=6),
        blocker=Blocker(),
        renderable=Renderable(glyph="g", label="goblin"),
    )
    return ContentPack(
        name="reference-vale", areas=(village,), entities=(player, goblin)
    )
