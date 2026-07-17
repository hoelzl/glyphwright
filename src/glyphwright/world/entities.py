"""Entities as component bags.

Component-based design without full-ECS machinery: GlyphWright needs clarity,
not archetype iteration throughput (design 0003 section 8.1). Entity ids are
stable and human-meaningful, so they read well in events and transcripts.
"""

from __future__ import annotations

from dataclasses import dataclass

from glyphwright.world.space import EntityId, PosId


@dataclass(frozen=True, slots=True)
class Position:
    """Where an entity stands."""

    at: PosId


@dataclass(frozen=True, slots=True)
class Actor:
    """An entity that takes turns and can be summarised in a frame."""

    name: str
    hp: int
    max_hp: int
    base_stats: tuple[tuple[str, int], ...] = ()

    def base_stat(self, stat: str) -> int:
        for name, value in self.base_stats:
            if name == stat:
                return value
        return 0


@dataclass(frozen=True, slots=True)
class Blocker:
    """Occupying entity that prevents others from entering its position."""


@dataclass(frozen=True, slots=True)
class Renderable:
    """The glyph a presentation may use for this entity, and what it means.

    The label feeds the frame's legend, so glyph vocabulary is content, not
    engine code.
    """

    glyph: str
    label: str


@dataclass(frozen=True, slots=True)
class StatModifier:
    """One contribution to a stat, as component data.

    ``op`` is ``add`` or ``mul``; multiplicative values are integer percentages
    (120 means +20%) so the pipeline stays in exact integer arithmetic (design
    0003 section 9.1). The pipeline itself lives in ``effects.stats``.
    """

    stat: str
    op: str
    value: int

    def __post_init__(self) -> None:
        # A typo'd op must be unrepresentable: silently contributing nothing
        # would make the provenance pipeline lie about what it considered.
        if self.op not in ("add", "mul"):
            raise ValueError(f"unknown modifier op: {self.op!r} (use 'add' or 'mul')")


@dataclass(frozen=True, slots=True)
class AiBehavior:
    """An AI-controlled actor's disposition.

    Hostiles are passive until provoked — by being attacked, or by the player
    stepping adjacent — and aggression is recorded as a world flag so it
    replays like every other state change. An ``engages`` hostile opens a
    formal menu battle on contact instead of trading skirmish blows.
    """

    hostile: bool = True
    engages: bool = False


@dataclass(frozen=True, slots=True)
class Item:
    """An entity that can be carried."""

    name: str


@dataclass(frozen=True, slots=True)
class Consumable:
    """An item destroyed by use. Slice 2's only use effect is healing."""

    heal: int


@dataclass(frozen=True, slots=True)
class Equippable:
    """An item that occupies a slot and contributes stat modifiers while worn."""

    slot: str
    modifiers: tuple[StatModifier, ...] = ()


@dataclass(frozen=True, slots=True)
class Inventory:
    """Item entity ids carried, in acquisition order."""

    items: tuple[EntityId, ...] = ()


@dataclass(frozen=True, slots=True)
class Equipment:
    """Worn items: slot -> item id, kept sorted by slot for determinism.

    Equipped items remain in the inventory; this component only records which
    slot they currently fill.
    """

    slots: tuple[tuple[str, EntityId], ...] = ()

    def in_slot(self, slot: str) -> EntityId | None:
        for name, item in self.slots:
            if name == slot:
                return item
        return None

    def equipped_items(self) -> tuple[EntityId, ...]:
        return tuple(item for _, item in self.slots)

    def with_slot(self, slot: str, item: EntityId) -> Equipment:
        kept = tuple(pair for pair in self.slots if pair[0] != slot)
        return Equipment(slots=tuple(sorted((*kept, (slot, item)))))


@dataclass(frozen=True, slots=True)
class Entity:
    """A stable id plus the components it carries."""

    id: EntityId
    position: Position | None = None
    actor: Actor | None = None
    blocker: Blocker | None = None
    renderable: Renderable | None = None
    ai: AiBehavior | None = None
    item: Item | None = None
    consumable: Consumable | None = None
    equippable: Equippable | None = None
    inventory: Inventory | None = None
    equipment: Equipment | None = None

    def at(self) -> PosId | None:
        return self.position.at if self.position is not None else None

    def carries(self) -> tuple[EntityId, ...]:
        return self.inventory.items if self.inventory is not None else ()
