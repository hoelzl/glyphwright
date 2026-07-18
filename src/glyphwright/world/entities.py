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
    """An entity that takes turns and can be summarised in a frame.

    ``perks`` are permanent statuses (design 0003 §9.3): each id names a
    status definition whose modifiers and hooks apply without an expiry
    clock.
    """

    name: str
    hp: int
    max_hp: int
    base_stats: tuple[tuple[str, int], ...] = ()
    abilities: tuple[str, ...] = ()
    perks: tuple[str, ...] = ()

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
    arena: str | None = None


@dataclass(frozen=True, slots=True)
class Portal:
    """A traversable link between areas.

    A portal entity stands at a position and contributes one extra exit token
    there; its twin at the destination authored explicitly, like room exits
    (design 0003 §7.4).
    """

    token: str
    to: PosId


@dataclass(frozen=True, slots=True)
class DialogueChoice:
    """One numbered option: prose, an optional flag, and where it leads."""

    text: str
    next: str | None = None
    sets_flag: str | None = None


@dataclass(frozen=True, slots=True)
class DialogueNode:
    """One beat of a conversation."""

    id: str
    line: str
    choices: tuple[DialogueChoice, ...]


@dataclass(frozen=True, slots=True)
class Dialogue:
    """An authored conversation tree (design 0003 §10.2).

    Trees are content; the dialogue mode walks them and emits events.
    Construction enforces what a soft-lock would otherwise punish at play
    time: unique node ids, resolvable links, no choiceless nodes, and a
    farewell reachable from the root.
    """

    root: str
    nodes: tuple[DialogueNode, ...]

    def __post_init__(self) -> None:
        ids = [node.id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("dialogue node ids must be unique")
        if self.root not in ids:
            raise ValueError(f"dialogue root {self.root!r} is not a node")
        for node in self.nodes:
            if not node.choices:
                raise ValueError(f"dialogue node {node.id!r} offers no choices")
            for choice in node.choices:
                if choice.next is not None and choice.next not in ids:
                    raise ValueError(
                        f"dialogue node {node.id!r} choice leads to unknown "
                        f"node {choice.next!r}"
                    )
        # A conversation the player can never leave is a soft-locked run:
        # some node reachable from the root must offer a way out.
        reachable = {self.root}
        frontier = [self.root]
        while frontier:
            node = self.node(frontier.pop())
            for choice in node.choices:
                if choice.next is None:
                    return
                if choice.next not in reachable:
                    reachable.add(choice.next)
                    frontier.append(choice.next)
        raise ValueError(f"dialogue rooted at {self.root!r} has no reachable farewell")

    def node(self, node_id: str) -> DialogueNode:
        for node in self.nodes:
            if node.id == node_id:
                return node
        raise KeyError(f"no such dialogue node: {node_id}")


@dataclass(frozen=True, slots=True)
class Openable:
    """A container: what it holds, and what its lock answers to.

    ``key`` names an item that opens it outright; without the key, opening
    pushes the lockpicking minigame.
    """

    contains: EntityId
    key: EntityId | None = None


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
class Statuses:
    """Timed status applications: ``(status-id, expires-turn)`` pairs.

    Definitions live in the content pack; this component records what is
    active on this entity right now, written and cleared by the fold.
    """

    active: tuple[tuple[str, int], ...] = ()

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(status for status, _ in self.active))

    def with_status(self, status: str, expires: int) -> Statuses:
        # A refresh extends the clock; it never truncates a longer one.
        for existing, current in self.active:
            if existing == status:
                expires = max(expires, current)
        kept = tuple(pair for pair in self.active if pair[0] != status)
        return Statuses(active=tuple(sorted((*kept, (status, expires)))))

    def without_status(self, status: str) -> Statuses:
        return Statuses(active=tuple(pair for pair in self.active if pair[0] != status))


@dataclass(frozen=True, slots=True)
class Entity:
    """A stable id plus the components it carries."""

    id: EntityId
    position: Position | None = None
    actor: Actor | None = None
    blocker: Blocker | None = None
    renderable: Renderable | None = None
    ai: AiBehavior | None = None
    portal: Portal | None = None
    dialogue: Dialogue | None = None
    openable: Openable | None = None
    statuses: Statuses | None = None
    item: Item | None = None
    consumable: Consumable | None = None
    equippable: Equippable | None = None
    inventory: Inventory | None = None
    equipment: Equipment | None = None

    def at(self) -> PosId | None:
        return self.position.at if self.position is not None else None

    def carries(self) -> tuple[EntityId, ...]:
        return self.inventory.items if self.inventory is not None else ()
