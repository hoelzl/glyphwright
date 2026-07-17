"""The strike: one attack resolved through the stat pipeline and the RNG.

Both the player's ``attack`` command and AI turns resolve through this one
function, so combat behaves — and replays — identically no matter who swings
(design 0003 sections 5.5, 9.1).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from glyphwright.effects.stats import derive
from glyphwright.kernel.events import (
    ActorDied,
    AttackMissed,
    DamageDealt,
    Event,
    FlagSet,
)
from glyphwright.kernel.rng import Rng
from glyphwright.world.space import EntityId

if TYPE_CHECKING:
    from glyphwright.kernel.state import WorldState

PLAYER_DEFEATED = "player-defeated"

_ABILITY = "strike"
_DAMAGE_TYPE = "physical"


def strike(
    state: WorldState, attacker: EntityId, defender: EntityId, rng: Rng
) -> tuple[tuple[Event, ...], Rng]:
    """Resolve one attack: to-hit, damage, and death or defeat.

    To hit: d20 + atk >= 10 + def. Damage: 1..atk, reduced by def // 2, never
    below 1. The defender's death removes it from the world — except the
    player, whose defeat is a world flag: the world must survive its
    protagonist.
    """
    atk = derive(state, attacker, "atk").value
    defence = derive(state, defender, "def").value

    roll, rng = rng.between(1, 20)
    if roll + atk < 10 + defence:
        return (AttackMissed(source=attacker, target=defender, ability=_ABILITY),), rng

    damage_roll, rng = rng.between(1, max(1, atk))
    amount = max(1, damage_roll - defence // 2)
    events: list[Event] = [
        DamageDealt(
            source=attacker,
            target=defender,
            ability=_ABILITY,
            damage_type=_DAMAGE_TYPE,
            amount=amount,
        )
    ]

    victim = state.entity(defender).actor
    if victim is not None and victim.hp - amount <= 0:
        from glyphwright.kernel.state import PLAYER

        if defender == PLAYER:
            events.append(FlagSet(flag=PLAYER_DEFEATED, value=True))
        else:
            events.append(ActorDied(actor=defender))
    return tuple(events), rng
