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
    Dialogue,
    DialogueChoice,
    DialogueNode,
    Entity,
    Equippable,
    Item,
    Openable,
    Portal,
    Position,
    Renderable,
    StatModifier,
)
from glyphwright.world.grid import GridSpace
from glyphwright.world.roomgraph import Room, RoomGraphSpace
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
_REFERENCE_BANDIT_AT = (1, 3)
_REFERENCE_DOOR_AT = (7, 1)

_INN_AREA = "inn"
_INN_ROOMS = (
    Room(
        id="common-room",
        name="The Gilded Tankard",
        description=(
            "Lamplight pools on scarred oak tables, and the air is thick "
            "with woodsmoke and spilled ale."
        ),
        exits=(("down", "cellar"),),
    ),
    Room(
        id="cellar",
        name="Inn Cellar",
        description=(
            "Casks line the walls of this low vault, and something small "
            "glints between the flagstones."
        ),
        exits=(("up", "common-room"),),
    ),
)


@dataclass(frozen=True, slots=True)
class ContentPack:
    """Validated content plus the hash that identifies it.

    Construction validates the cross-area wiring — a portal must stand on a
    real position, lead to a real position, and neither shadow a geometric
    exit nor collide with another portal — because a load-time diagnostic
    beats a mid-session crash (0003 §8.2).
    """

    name: str
    areas: tuple[GridSpace | RoomGraphSpace, ...]
    entities: tuple[Entity, ...]

    def __post_init__(self) -> None:
        spaces = {space.area: space for space in self.areas}
        if len(spaces) != len(self.areas):
            raise ValueError("area ids must be unique")
        claimed: set[tuple[str, str]] = set()
        for entity in self.entities:
            portal = entity.portal
            if portal is None:
                continue
            at = entity.at()
            if at is None:
                raise ValueError(f"portal {entity.id!r} stands nowhere")
            if at.area not in spaces or not spaces[at.area].contains(at):
                raise ValueError(f"portal {entity.id!r} stands off the map: {at}")
            if portal.to.area not in spaces or not spaces[portal.to.area].contains(
                portal.to
            ):
                raise ValueError(f"portal {entity.id!r} leads nowhere: {portal.to}")
            if portal.token in spaces[at.area].exits(at):
                raise ValueError(
                    f"portal {entity.id!r} token {portal.token!r} shadows a "
                    f"geometric exit at {at}"
                )
            key = (str(at), portal.token)
            if key in claimed:
                raise ValueError(
                    f"two portals at {at} claim the token {portal.token!r}"
                )
            claimed.add(key)

    @property
    def pack_id(self) -> str:
        """A stable ``name@sha256:…`` identifier over canonical content.

        Hashing walks every field via ``asdict``, so adding a component or an
        area kind automatically widens the identity — a pack cannot change
        content without changing its id.
        """

        def canonical_area(space: GridSpace | RoomGraphSpace) -> dict[str, object]:
            fields = asdict(space)
            fields["area"] = fields.pop("_area")
            fields["kind"] = type(space).__name__
            return fields

        payload = json.dumps(
            {
                "name": self.name,
                "areas": [canonical_area(space) for space in self.areas],
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
            base_stats=(("atk", 5), ("def", 3), ("spd", 5)),
        ),
        blocker=Blocker(),
        renderable=Renderable(glyph="@", label="player"),
    )
    potion = Entity(
        id="potion-minor",
        position=Position(at=space.pos(*_REFERENCE_POTION_AT)),
        item=Item(name="Minor Potion"),
        consumable=Consumable(heal=6),
        renderable=Renderable(glyph="!", label="potion"),
    )
    sword = Entity(
        id="iron-sword",
        position=Position(at=space.pos(*_REFERENCE_SWORD_AT)),
        item=Item(name="Iron Sword"),
        equippable=Equippable(
            slot="weapon",
            modifiers=(StatModifier(stat="atk", op="add", value=3),),
        ),
        renderable=Renderable(glyph="/", label="weapon"),
    )
    goblin = Entity(
        id="goblin-1",
        position=Position(at=space.pos(*_REFERENCE_GOBLIN_AT)),
        actor=Actor(
            name="Goblin",
            hp=6,
            max_hp=6,
            base_stats=(("atk", 3), ("def", 1), ("spd", 3)),
        ),
        blocker=Blocker(),
        renderable=Renderable(glyph="g", label="goblin"),
        ai=AiBehavior(hostile=True),
    )
    bandit = Entity(
        id="bandit-1",
        position=Position(at=space.pos(*_REFERENCE_BANDIT_AT)),
        actor=Actor(
            name="Bandit",
            hp=8,
            max_hp=8,
            base_stats=(("atk", 4), ("def", 2), ("spd", 4)),
        ),
        blocker=Blocker(),
        renderable=Renderable(glyph="b", label="bandit"),
        ai=AiBehavior(hostile=True, engages=True),
    )
    inn = RoomGraphSpace(_area=_INN_AREA, rooms=_INN_ROOMS)
    inn_door = Entity(
        id="inn-door",
        position=Position(at=space.pos(*_REFERENCE_DOOR_AT)),
        portal=Portal(token="enter", to=inn.pos("common-room")),
        renderable=Renderable(glyph="+", label="door"),
    )
    inn_exit = Entity(
        id="inn-exit",
        position=Position(at=inn.pos("common-room")),
        portal=Portal(token="out", to=space.pos(*_REFERENCE_DOOR_AT)),
    )
    key = Entity(
        id="rusty-key",
        position=Position(at=inn.pos("cellar")),
        item=Item(name="Rusty Key"),
    )
    innkeeper = Entity(
        id="innkeeper",
        position=Position(at=inn.pos("common-room")),
        actor=Actor(
            name="Osric",
            hp=10,
            max_hp=10,
            base_stats=(("atk", 2), ("def", 2), ("spd", 3)),
        ),
        dialogue=Dialogue(
            root="greeting",
            nodes=(
                DialogueNode(
                    id="greeting",
                    line=("Wind's teeth, a traveller! Warm yourself — what'll it be?"),
                    choices=(
                        DialogueChoice(
                            text="Ask about the cellar",
                            next="cellar",
                            sets_flag="heard-cellar-rumor",
                        ),
                        DialogueChoice(text="Ask about the road", next="road"),
                        DialogueChoice(text="Take your leave", next=None),
                    ),
                ),
                DialogueNode(
                    id="cellar",
                    line=(
                        "The old strongbox? Lost the key years back. If you "
                        "can charm it open, keep what you find."
                    ),
                    choices=(
                        DialogueChoice(text="Ask about the road", next="road"),
                        DialogueChoice(text="Take your leave", next=None),
                    ),
                ),
                DialogueNode(
                    id="road",
                    line=(
                        "A goblin skulks by the south wall, and that bandit "
                        "by the door is no friend of yours either."
                    ),
                    choices=(
                        DialogueChoice(
                            text="Ask about the cellar",
                            next="cellar",
                            sets_flag="heard-cellar-rumor",
                        ),
                        DialogueChoice(text="Take your leave", next=None),
                    ),
                ),
            ),
        ),
    )
    strongbox = Entity(
        id="strongbox",
        position=Position(at=inn.pos("cellar")),
        openable=Openable(contains="silver-locket", key="rusty-key"),
    )
    locket = Entity(
        id="silver-locket",
        item=Item(name="Silver Locket"),
    )
    return ContentPack(
        name="reference-vale",
        areas=(space, inn),
        entities=(
            player,
            potion,
            sword,
            goblin,
            bandit,
            inn_door,
            inn_exit,
            key,
            innkeeper,
            strongbox,
            locket,
        ),
    )
