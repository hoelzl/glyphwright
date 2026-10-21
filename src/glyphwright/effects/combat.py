"""The strike and the initiative roll, resolved through the stat pipeline.

Both the player's ``attack`` and every foe's turn resolve through ``strike``,
so combat behaves, and replays, identically no matter who swings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from glyphwright.effects.stats import derive
from glyphwright.kernel.events import (
    ActorDied,
    AttackMissed,
    DamageDealt,
    Defeated,
    Event,
)
from glyphwright.kernel.rng import Rng
from glyphwright.world.entities import Entity
from glyphwright.world.space import EntityId, PosId

if TYPE_CHECKING:
    from glyphwright.kernel.state import WorldState


def hostile_actors(state: WorldState) -> tuple[Entity, ...]:
    """Every living hostile in the world, in sorted-id order."""
    return tuple(
        entity
        for _, entity in sorted(state.entities.items())
        if entity.ai is not None and entity.ai.hostile and entity.actor is not None
    )


def melee_adjacent(state: WorldState, a: PosId, b: PosId) -> bool:
    """Whether ``b`` is one geometric step from ``a`` in the same area.

    v0 finding D6: v0 asked the geometry through a ``melee_range`` method
    added to the ``Space`` protocol without recording it. One step through the
    space's own exits answers the same question for a grid. Portals do not
    count: melee happens within one area.
    """
    return a.area == b.area and b in state.areas[a.area].exits(a).values()


def roll_initiative(
    state: WorldState, combatants: tuple[EntityId, ...], rng: Rng
) -> tuple[tuple[EntityId, ...], Rng]:
    """Roll d20 + spd per combatant; highest first, ties by id.

    The rolls happen in sorted-id order, so identical states draw identically.
    """
    scored: list[tuple[int, EntityId]] = []
    for combatant in sorted(combatants):
        roll, rng = rng.between(1, 20)
        scored.append((-(roll + derive(state, combatant, "spd").value), combatant))
    return tuple(combatant for _, combatant in sorted(scored)), rng


def strike(
    state: WorldState, attacker: EntityId, defender: EntityId, rng: Rng
) -> tuple[tuple[Event, ...], Rng]:
    """Resolve one attack: to hit, damage, then death or defeat.

    To hit: d20 + atk >= 10 + def. Damage: 1 to atk, reduced by def // 2, at
    least 1. A foe at 0 hp dies and leaves the world; the player is defeated
    and stays.
    """
    from glyphwright.kernel.state import PLAYER

    atk = derive(state, attacker, "atk").value
    defence = derive(state, defender, "def").value

    roll, rng = rng.between(1, 20)
    if roll + atk < 10 + defence:
        return (AttackMissed(source=attacker, target=defender),), rng

    damage_roll, rng = rng.between(1, max(1, atk))
    amount = max(1, damage_roll - defence // 2)
    events: list[Event] = [DamageDealt(source=attacker, target=defender, amount=amount)]
    victim = state.entity(defender).actor
    if victim is not None and victim.hp - amount <= 0:
        events.append(
            Defeated(actor=defender)
            if defender == PLAYER
            else ActorDied(actor=defender)
        )
    return tuple(events), rng
