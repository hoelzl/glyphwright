"""Immutable world state, and the fold that turns events into successors.

State is immutable so snapshots are free, replay and undo are trivial, and tests
can assert that ``step`` did not mutate its input. Performance is irrelevant at
terminal-game scale.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import assert_never

from glyphwright.kernel.events import (
    ActorDied,
    AttackMissed,
    DamageDealt,
    Defeated,
    Event,
    FleeFailed,
    Healed,
    ItemAcquired,
    ItemEquipped,
    ItemUsed,
    ModePopped,
    ModePushed,
    MoveBlocked,
    Moved,
    Provoked,
    TurnAdvanced,
)
from glyphwright.kernel.rng import Rng
from glyphwright.world.entities import Entity, Equipment, Inventory, Position
from glyphwright.world.space import EntityId, ExitToken, PosId, Space

PLAYER: EntityId = "player"

# Mode names are kernel vocabulary: the fold branches on them, and the kernel
# cannot import the modes package (modes import the kernel).
MODE_EXPLORATION = "exploration"
MODE_BATTLE = "battle"
BATTLE_OUTCOMES = ("victory", "defeat", "fled")


@dataclass(frozen=True, slots=True)
class WorldState:
    """Everything needed to resolve a turn.

    Later slices add fields with defaults, so states built by earlier code keep
    constructing unchanged.
    """

    entities: Mapping[EntityId, Entity]
    areas: Mapping[str, Space]
    mode_stack: tuple[str, ...]
    turn: int
    rng: Rng
    # Who acts after the player in the current battle, in order; empty
    # outside a battle.
    initiative: tuple[EntityId, ...] = ()

    def __post_init__(self) -> None:
        # Freeze the mappings so "immutable" is enforced rather than promised.
        object.__setattr__(self, "entities", MappingProxyType(dict(self.entities)))
        object.__setattr__(self, "areas", MappingProxyType(dict(self.areas)))
        if not self.mode_stack:
            raise ValueError("the mode stack must never be empty")

    @property
    def mode(self) -> str:
        return self.mode_stack[-1]

    @property
    def defeated(self) -> bool:
        """Whether the player is at 0 hp: then only ``look`` is left."""
        actor = self.entity(PLAYER).actor
        return actor is not None and actor.hp <= 0

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

    def exits_from(self, pos: PosId) -> dict[ExitToken, PosId]:
        """The movement graph out of ``pos``: the space's exits plus any portal
        standing there.

        Everything that moves reads exits through here, so a door the player
        can use is a door every mover can use. A portal token never shadows a
        geometric exit: content validation refuses that at load.
        """
        merged = dict(self.areas[pos.area].exits(pos))
        for entity in self.entities_at(pos):
            if entity.portal is not None:
                merged[entity.portal.token] = entity.portal.to
        return merged

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
    replay from a log and snapshot/restore equivalent.
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
            if event.rng is not None:
                return replace(state, turn=event.turn, rng=Rng.decode(event.rng))
            return replace(state, turn=event.turn)
        case ItemAcquired():
            item = replace(state.entity(event.item), position=None)
            actor = state.entity(event.actor)
            carried = (*actor.carries(), event.item)
            actor = replace(actor, inventory=Inventory(items=carried))
            return state.with_entity(item).with_entity(actor)
        case ItemUsed():
            actor = state.entity(event.actor)
            kept = tuple(i for i in actor.carries() if i != event.item)
            actor = replace(actor, inventory=Inventory(items=kept))
            if actor.equipment is not None:
                # A consumed item must not leave a dangling slot reference.
                slots = tuple(
                    pair for pair in actor.equipment.slots if pair[1] != event.item
                )
                actor = replace(actor, equipment=Equipment(slots=slots))
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
            # v0 finding K5: without the lower clamp, a negative amount drove hp
            # below zero. Content refuses such amounts; the fold is safe anyway.
            hp = min(max(target.actor.hp + event.amount, 0), target.actor.max_hp)
            return state.with_entity(
                replace(target, actor=replace(target.actor, hp=hp))
            )
        case Provoked():
            hostile = state.entity(event.actor)
            if hostile.ai is None:
                raise ValueError(f"Provoked actor {event.actor} has no ai")
            return state.with_entity(
                replace(hostile, ai=replace(hostile.ai, aggroed=True))
            )
        case DamageDealt():
            target = state.entity(event.target)
            if target.actor is None:
                raise ValueError(f"DamageDealt target {event.target} is not an actor")
            hp = max(target.actor.hp - event.amount, 0)
            return state.with_entity(
                replace(target, actor=replace(target.actor, hp=hp))
            )
        case ActorDied():
            if event.actor == PLAYER:
                raise ValueError("the player is defeated, never removed")
            # The dead leave no initiative slot behind.
            survivors = state.without_entity(event.actor)
            return replace(
                survivors,
                initiative=tuple(i for i in state.initiative if i != event.actor),
            )
        case ModePushed():
            return replace(
                state,
                mode_stack=(*state.mode_stack, event.mode),
                initiative=event.initiative or state.initiative,
            )
        case ModePopped():
            if state.mode != event.mode:
                raise ValueError(
                    f"cannot pop {event.mode!r}: the active mode is {state.mode!r}"
                )
            initiative = () if event.mode == MODE_BATTLE else state.initiative
            return replace(
                state, mode_stack=state.mode_stack[:-1], initiative=initiative
            )
        case AttackMissed() | Defeated() | FleeFailed():
            return state
        case _:
            assert_never(event)


def fold(state: WorldState, events: tuple[Event, ...]) -> WorldState:
    """Apply events in order, returning the successor state."""
    for event in events:
        state = apply(state, event)
    return state
