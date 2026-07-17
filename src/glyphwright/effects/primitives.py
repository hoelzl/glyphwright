"""Effect primitives: the Python-implemented vocabulary content composes.

There is no scripting language (0003 §9.2): content names primitives and
parameterizes them, and everything executes inside ``step`` — deterministic
and event-producing. Unknown names are load-time errors, not runtime
surprises.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from glyphwright.effects.combat import resolve_damage
from glyphwright.effects.stats import derive
from glyphwright.kernel.events import Event, Healed, StatusApplied
from glyphwright.kernel.rng import Rng
from glyphwright.world.space import EntityId

if TYPE_CHECKING:
    from glyphwright.kernel.state import WorldState


def _int_param(params: Mapping[str, object], key: str, default: int = 0) -> int:
    value = params.get(key, default)
    assert isinstance(value, int), f"primitive parameter {key!r} must be an integer"
    return value


Primitive = Callable[
    ["WorldState", EntityId, EntityId, Mapping[str, object], Rng],
    tuple[tuple[Event, ...], Rng],
]


def _deal_damage(
    state: WorldState,
    source: EntityId,
    target: EntityId,
    params: Mapping[str, object],
    rng: Rng,
) -> tuple[tuple[Event, ...], Rng]:
    amount = _int_param(params, "amount", 1)
    spread = _int_param(params, "spread", 0)
    ability = str(params.get("ability", "effect"))
    if spread:
        extra, rng = rng.between(0, spread)
        amount += extra
    defence = derive(state, target, "def").value
    dealt = max(1, amount - defence // 2)
    return resolve_damage(
        state, source, target, ability=ability, damage_type="arcane", amount=dealt
    ), rng


def _heal(
    state: WorldState,
    source: EntityId,
    target: EntityId,
    params: Mapping[str, object],
    rng: Rng,
) -> tuple[tuple[Event, ...], Rng]:
    actor = state.entity(target).actor
    assert actor is not None, "content validation admits only actor targets"
    amount = min(_int_param(params, "amount", 1), actor.max_hp - actor.hp)
    return (Healed(target=target, amount=amount, source=source),), rng


def _apply_status(
    state: WorldState,
    source: EntityId,
    target: EntityId,
    params: Mapping[str, object],
    rng: Rng,
) -> tuple[tuple[Event, ...], Rng]:
    status = str(params["status"])
    duration = _int_param(params, "duration", 1)
    return (
        StatusApplied(target=target, status=status, expires=state.turn + duration),
    ), rng


PRIMITIVES: dict[str, Primitive] = {
    "deal_damage": _deal_damage,
    "heal": _heal,
    "apply_status": _apply_status,
}
