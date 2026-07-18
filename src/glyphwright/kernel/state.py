"""Immutable world state, and the fold that turns events into successors.

State is immutable so snapshots are free, replay and undo are trivial, and tests
can assert that ``step`` did not mutate its input (design 0003 section 5.2,
ADR-002). Performance is irrelevant at terminal-game scale.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import TYPE_CHECKING

from glyphwright.kernel.events import (
    ActorDied,
    AttackMissed,
    CastFizzled,
    ChoiceOffered,
    DamageDealt,
    DialogueLine,
    Event,
    FlagSet,
    FleeFailed,
    FocusSet,
    Healed,
    ItemAcquired,
    ItemEquipped,
    ItemUsed,
    MinigameResolved,
    ModePopped,
    ModePushed,
    MoveBlocked,
    Moved,
    PerkGained,
    PinSet,
    PinSlipped,
    StatusApplied,
    StatusExpired,
    TurnAdvanced,
    aggro_flag,
)
from glyphwright.kernel.rng import Rng
from glyphwright.world.entities import (
    Entity,
    Equipment,
    Inventory,
    Position,
    Statuses,
)
from glyphwright.world.space import EntityId, PosId, Space

if TYPE_CHECKING:
    from glyphwright.effects.abilities import Ability, Status

PLAYER: EntityId = "player"

# Mode names are kernel vocabulary: the scheduler and the fold both branch on
# them, and the kernel cannot import the modes package (modes import kernel).
MODE_EXPLORATION = "exploration"
MODE_BATTLE = "battle"
MODE_DIALOGUE = "dialogue"
MODE_LOCKPICK = "minigame:lockpick"

# Modes whose per-mode cursor lives in ``WorldState.focus``. Popping one
# clears the focus; popping anything else (a battle atop a conversation)
# must leave the underlying mode's cursor intact.
FOCUS_MODES = frozenset({MODE_DIALOGUE, MODE_LOCKPICK})


@dataclass(frozen=True, slots=True)
class WorldState:
    """Everything needed to resolve a turn."""

    entities: Mapping[EntityId, Entity]
    areas: Mapping[str, Space]
    mode_stack: tuple[str, ...]
    turn: int
    rng: Rng
    flags: Mapping[str, bool]
    initiative: tuple[EntityId, ...] = ()
    focus: tuple[EntityId, str] | None = None
    battle_returns: tuple[tuple[EntityId, PosId], ...] = ()
    ability_defs: Mapping[str, Ability] = field(default_factory=dict)
    status_defs: Mapping[str, Status] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Freeze the mappings so "immutable" is enforced rather than promised.
        object.__setattr__(self, "entities", MappingProxyType(dict(self.entities)))
        object.__setattr__(self, "areas", MappingProxyType(dict(self.areas)))
        object.__setattr__(self, "flags", MappingProxyType(dict(self.flags)))
        object.__setattr__(
            self, "ability_defs", MappingProxyType(dict(self.ability_defs))
        )
        object.__setattr__(
            self, "status_defs", MappingProxyType(dict(self.status_defs))
        )
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

    def exits_from(self, pos: PosId) -> dict[str, PosId]:
        """The position's space exits plus any portal standing there.

        This is the one movement graph — the player's grammar and the AI's
        pursuit both read it, so a door the player can use is a door a
        pursuer can follow through (0003 §7.4).
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
            if event.rng is not None:
                return replace(state, turn=event.turn, rng=Rng.decode(event.rng))
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
            # The dead leave no dangling aggression, and no initiative slot.
            survivors = state.without_entity(event.actor)
            if event.actor in survivors.initiative:
                survivors = replace(
                    survivors,
                    initiative=tuple(
                        i for i in survivors.initiative if i != event.actor
                    ),
                )
            if aggro_flag(event.actor) in survivors.flags:
                flags = dict(survivors.flags)
                del flags[aggro_flag(event.actor)]
                return replace(survivors, flags=flags)
            return survivors
        case ModePushed():
            # A push without an initiative payload (a future dialogue or menu
            # atop a battle) must not wipe the battle's queue beneath it; the
            # same preservation rule guards the way home.
            initiative = event.initiative if event.initiative else state.initiative
            returns = event.returns if event.returns else state.battle_returns
            return replace(
                state,
                mode_stack=(*state.mode_stack, event.mode),
                initiative=initiative,
                battle_returns=returns,
            )
        case ModePopped():
            if state.mode != event.mode:
                raise ValueError(
                    f"cannot pop {event.mode!r}: the active mode is {state.mode!r}"
                )
            initiative = () if event.mode == MODE_BATTLE else state.initiative
            returns = () if event.mode == MODE_BATTLE else state.battle_returns
            focus = None if event.mode in FOCUS_MODES else state.focus
            return replace(
                state,
                mode_stack=state.mode_stack[:-1],
                initiative=initiative,
                battle_returns=returns,
                focus=focus,
            )
        case FleeFailed():
            return state
        case FocusSet():
            return replace(state, focus=(event.entity, event.detail))
        case DialogueLine() | ChoiceOffered() | PinSet() | PinSlipped():
            # Pure evidence: the cursor moves through FocusSet.
            return state
        case MinigameResolved():
            return state
        case StatusApplied():
            target = state.entity(event.target)
            bearing = target.statuses or Statuses()
            return state.with_entity(
                replace(
                    target,
                    statuses=bearing.with_status(event.status, event.expires),
                )
            )
        case StatusExpired():
            target = state.entity(event.target)
            bearing = target.statuses or Statuses()
            return state.with_entity(
                replace(target, statuses=bearing.without_status(event.status))
            )
        case PerkGained():
            target = state.entity(event.target)
            assert target.actor is not None, "only actors gain perks"
            if event.perk in target.actor.perks:
                return state
            return state.with_entity(
                replace(
                    target,
                    actor=replace(
                        target.actor, perks=(*target.actor.perks, event.perk)
                    ),
                )
            )
        case CastFizzled():
            return state
        case FlagSet():
            flags = dict(state.flags)
            flags[event.flag] = event.value
            return replace(state, flags=flags)


def fold(state: WorldState, events: tuple[Event, ...]) -> WorldState:
    """Apply events in order, returning the successor state."""
    for event in events:
        state = apply(state, event)
    return state
