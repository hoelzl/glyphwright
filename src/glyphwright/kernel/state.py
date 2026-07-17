"""Immutable world state, and the fold that turns events into successors.

State is immutable so snapshots are free, replay and undo are trivial, and tests
can assert that ``step`` did not mutate its input (design 0003 section 5.2,
ADR-002). Performance is irrelevant at terminal-game scale.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType

from glyphwright.kernel.events import (
    ActorDied,
    AttackMissed,
    DamageDealt,
    Event,
    FlagSet,
    Healed,
    ItemAcquired,
    ItemEquipped,
    ItemUsed,
    MoveBlocked,
    Moved,
    TurnAdvanced,
)
from glyphwright.kernel.rng import Rng
from glyphwright.world.entities import Entity, Equipment, Inventory, Position
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

    def without_entity(self, entity_id: EntityId) -> WorldState:
        entities = dict(self.entities)
        del entities[entity_id]
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
        case ItemAcquired():
            item = replace(state.entity(event.item), position=None)
            actor = state.entity(event.actor)
            carried = actor.inventory or Inventory()
            actor = replace(
                actor, inventory=Inventory(items=(*carried.items, event.item))
            )
            return state.with_entity(item).with_entity(actor)
        case ItemUsed():
            if not event.consumed:
                return state
            actor = state.entity(event.actor)
            carried = actor.inventory or Inventory()
            actor = replace(
                actor,
                inventory=Inventory(
                    items=tuple(i for i in carried.items if i != event.item)
                ),
            )
            if actor.equipment is not None:
                # A consumed item must not leave a dangling slot reference.
                actor = replace(
                    actor,
                    equipment=Equipment(
                        slots=tuple(
                            pair
                            for pair in actor.equipment.slots
                            if pair[1] != event.item
                        )
                    ),
                )
            return state.with_entity(actor).without_entity(event.item)
        case ItemEquipped():
            actor = state.entity(event.actor)
            worn = actor.equipment or Equipment()
            return state.with_entity(
                replace(actor, equipment=worn.with_slot(event.slot, event.item))
            )
        case Healed():
            target = state.entity(event.target)
            if target.actor is None:
                raise ValueError(f"Healed target {event.target} is not an actor")
            healed = replace(
                target.actor,
                hp=min(target.actor.hp + event.amount, target.actor.max_hp),
            )
            return state.with_entity(replace(target, actor=healed))
        case DamageDealt():
            target = state.entity(event.target)
            if target.actor is None:
                raise ValueError(f"DamageDealt target {event.target} is not an actor")
            hurt = replace(target.actor, hp=max(target.actor.hp - event.amount, 0))
            return state.with_entity(replace(target, actor=hurt))
        case AttackMissed():
            return state
        case ActorDied():
            return state.without_entity(event.actor)
        case FlagSet():
            flags = dict(state.flags)
            flags[event.flag] = event.value
            return replace(state, flags=flags)


def fold(state: WorldState, events: tuple[Event, ...]) -> WorldState:
    """Apply events in order, returning the successor state."""
    for event in events:
        state = apply(state, event)
    return state
