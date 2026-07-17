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


@dataclass(frozen=True, slots=True)
class Blocker:
    """Occupying entity that prevents others from entering its position."""


@dataclass(frozen=True, slots=True)
class Renderable:
    """The glyph a presentation may use for this entity."""

    glyph: str


@dataclass(frozen=True, slots=True)
class Entity:
    """A stable id plus the components it carries."""

    id: EntityId
    position: Position | None = None
    actor: Actor | None = None
    blocker: Blocker | None = None
    renderable: Renderable | None = None

    def at(self) -> PosId | None:
        return self.position.at if self.position is not None else None
