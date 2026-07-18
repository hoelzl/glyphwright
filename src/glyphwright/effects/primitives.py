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
from glyphwright.kernel.events import Event, Healed, PerkGained, StatusApplied
from glyphwright.kernel.rng import Rng
from glyphwright.world.space import EntityId

if TYPE_CHECKING:
    from glyphwright.kernel.state import WorldState


# What each primitive accepts, used by pack validation so malformed params are
# load-time diagnostics, never mid-session crashes. "ability" is reserved: the
# engine injects the casting ability's (or hooking status's) id for evidence
# labelling. "pending_turn" is reserved: the chain runner injects whether the
# step's turn advance is still to come, so durations mean the same thing for
# every caster.
PARAM_SPECS: dict[str, dict[str, type]] = {
    "deal_damage": {"amount": int, "spread": int},
    "heal": {"amount": int},
    "apply_status": {"status": str, "duration": int},
    "grant_perk": {"perk": str},
}
RESERVED_PARAMS = frozenset({"ability", "pending_turn"})


def validate_params(primitive: str, params: Mapping[str, object]) -> None:
    """Raise ``ValueError`` unless ``params`` fit the primitive's spec."""
    spec = PARAM_SPECS[primitive]
    for key, value in params.items():
        if key in RESERVED_PARAMS:
            raise ValueError(
                f"primitive {primitive!r} parameter {key!r} is reserved for the engine"
            )
        if key not in spec:
            raise ValueError(f"primitive {primitive!r} takes no parameter {key!r}")
        if not isinstance(value, spec[key]) or isinstance(value, bool):
            raise ValueError(
                f"primitive {primitive!r} parameter {key!r} must be "
                f"{spec[key].__name__}, got {value!r}"
            )
    if primitive == "apply_status" and "status" not in params:
        raise ValueError("apply_status requires a 'status' parameter")
    if primitive == "grant_perk" and "perk" not in params:
        raise ValueError("grant_perk requires a 'perk' parameter")


def _int_param(params: Mapping[str, object], key: str, default: int = 0) -> int:
    value = params.get(key, default)
    if not isinstance(value, int):
        raise ValueError(f"primitive parameter {key!r} must be an integer")
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
    # A duration covers the holder's next `duration` turns. A player cast's
    # own turn advance is still pending, so it needs one extra tick of clock;
    # an AI cast or a hook runs after the advance already folded (design
    # 0004 §3, evened out across casters in 0007).
    pending = 1 if params.get("pending_turn") else 0
    return (
        StatusApplied(
            target=target, status=status, expires=state.turn + pending + duration
        ),
    ), rng


def _grant_perk(
    state: WorldState,
    source: EntityId,
    target: EntityId,
    params: Mapping[str, object],
    rng: Rng,
) -> tuple[tuple[Event, ...], Rng]:
    perk = str(params["perk"])
    return (PerkGained(target=target, perk=perk),), rng


PRIMITIVES: dict[str, Primitive] = {
    "deal_damage": _deal_damage,
    "heal": _heal,
    "apply_status": _apply_status,
    "grant_perk": _grant_perk,
}
