"""Entities as component bags.

Component-based design without full ECS machinery: GlyphWright needs clarity,
not archetype iteration throughput. Entity ids are stable and human-meaningful,
so they read well in events and transcripts. Later slices add components as
defaulted fields, so existing content keeps loading.
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
    """An entity that takes turns and can be summarised in a frame.

    ``base_stats`` are ``(stat, value)`` pairs, sorted by stat; equipment adds
    to them through the stat pipeline in ``effects.stats``.
    """

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
class Portal:
    """A traversable link to a position, usually in another area.

    A portal entity stands at a position and adds one exit token there. Its
    way back is a second portal, authored at the destination.
    """

    token: str
    to: PosId


MODIFIER_OPS = ("add", "mul")


@dataclass(frozen=True, slots=True)
class StatModifier:
    """One contribution to a stat, as component data.

    ``op`` is ``add`` or ``mul``; multiplicative values are integer percentages
    (120 means +20%), so the pipeline stays in exact integer arithmetic. The
    pipeline itself lives in ``effects.stats``.
    """

    stat: str
    op: str
    value: int

    def __post_init__(self) -> None:
        # A typo'd op must be unrepresentable: silently contributing nothing
        # would make the provenance pipeline lie about what it considered.
        if self.op not in MODIFIER_OPS:
            raise ValueError(f"unknown modifier op {self.op!r}: use 'add' or 'mul'")
        if self.op == "mul" and self.value < 0:
            # v2 finding N12: a negative percentage flips the stat's sign.
            raise ValueError(f"a 'mul' modifier needs a value >= 0, not {self.value}")


@dataclass(frozen=True, slots=True)
class Item:
    """An entity that can be carried."""

    name: str


@dataclass(frozen=True, slots=True)
class Consumable:
    """An item destroyed by use: it restores hp."""

    heal: int


@dataclass(frozen=True, slots=True)
class Equippable:
    """An item that fills a slot and contributes stat modifiers while worn."""

    slot: str
    modifiers: tuple[StatModifier, ...] = ()


@dataclass(frozen=True, slots=True)
class Inventory:
    """Item entity ids carried, in acquisition order."""

    items: tuple[EntityId, ...] = ()


@dataclass(frozen=True, slots=True)
class Equipment:
    """Worn items: slot to item id, kept sorted by slot for determinism.

    Equipped items stay in the inventory; this component only records which
    slot they fill.
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
    portal: Portal | None = None
    item: Item | None = None
    consumable: Consumable | None = None
    equippable: Equippable | None = None
    inventory: Inventory | None = None
    equipment: Equipment | None = None

    def at(self) -> PosId | None:
        return self.position.at if self.position is not None else None

    def carries(self) -> tuple[EntityId, ...]:
        return self.inventory.items if self.inventory is not None else ()
