"""Immutable world state, and the fold that turns events into successors.

State is immutable so snapshots are free, replay and undo are trivial, and tests
can assert that ``step`` did not mutate its input (design 0003 section 5.2,
ADR-002). Performance is irrelevant at terminal-game scale.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType

from glyphwright.kernel.events import Event, MoveBlocked, Moved, TurnAdvanced
from glyphwright.kernel.rng import Rng
from glyphwright.world.entities import Entity, Position
from glyphwright.world.space import EntityId, PosId, Space

PLAYER: EntityId = "player"


@dataclass(frozen=True, slots=True)
class WorldState:
    """Everything needed to resolve a turn."""

    entities: Mapping[EntityId, Entity]
    areas: Mapping[str, Space]
    mode_stack: tuple[str, ...]
    turn: int
    rng: Rng
    flags: Mapping[str, bool]

    def __post_init__(self) -> None:
        # Freeze the mappings so "immutable" is enforced rather than promised.
        object.__setattr__(self, "entities", MappingProxyType(dict(self.entities)))
        object.__setattr__(self, "areas", MappingProxyType(dict(self.areas)))
        object.__setattr__(self, "flags", MappingProxyType(dict(self.flags)))
        if not self.mode_stack:
            raise ValueError("the mode stack must never be empty")

    @property
    def mode(self) -> str:
        return self.mode_stack[-1]

    def entity(self, entity_id: EntityId) -> Entity:
        try:
            return self.entities[entity_id]
        except KeyError as error:
            raise KeyError(f"no such entity: {entity_id}") from error

    def entities_at(self, pos: PosId) -> tuple[Entity, ...]:
        return tuple(
            entity for _, entity in sorted(self.entities.items()) if entity.at() == pos
        )

    def space_of(self, entity_id: EntityId) -> Space:
        at = self.entity(entity_id).at()
        if at is None:
            raise ValueError(f"{entity_id} has no position")
        return self.areas[at.area]

    def with_entity(self, entity: Entity) -> WorldState:
        entities = dict(self.entities)
        entities[entity.id] = entity
        return replace(self, entities=entities)


def apply(state: WorldState, event: Event) -> WorldState:
    """Fold one event into a state.

    Every mutation in the engine flows through here, which is what makes
    replay-from-log and snapshot/restore equivalent.
    """
    match event:
        case Moved():
            entity = state.entity(event.actor)
            return state.with_entity(
                replace(entity, position=Position(at=event.destination))
            )
        case MoveBlocked():
            return state
        case TurnAdvanced():
            return replace(state, turn=event.turn)


def fold(state: WorldState, events: tuple[Event, ...]) -> WorldState:
    """Apply events in order, returning the successor state."""
    for event in events:
        state = apply(state, event)
    return state
