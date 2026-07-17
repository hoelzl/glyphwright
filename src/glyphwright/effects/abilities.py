"""Abilities and statuses as content data (design 0004, scoping 0003 §9).

An ability is requirements plus targeting plus an ordered list of effect
primitives; a status is a named bundle of stat modifiers with a duration
chosen at application time. Both are pack tables carried in world state so
handlers can resolve them without reaching outside the kernel's inputs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from glyphwright.effects.stats import derive
from glyphwright.kernel.events import CastFizzled, Event, TurnAdvanced
from glyphwright.kernel.rng import Rng
from glyphwright.world.entities import StatModifier
from glyphwright.world.space import EntityId

if TYPE_CHECKING:
    from glyphwright.kernel.state import WorldState

TARGET_SELF = "self"
TARGET_FOE = "foe"


@dataclass(frozen=True, slots=True)
class Ability:
    """Content: what the ability needs, whom it reaches, what it composes."""

    id: str
    name: str
    targeting: str
    effects: tuple[tuple[str, Mapping[str, object]], ...]
    requires_stat: tuple[str, int] | None = None

    def __post_init__(self) -> None:
        if self.targeting not in (TARGET_SELF, TARGET_FOE):
            raise ValueError(
                f"ability {self.id!r} has unknown targeting {self.targeting!r}"
            )


@dataclass(frozen=True, slots=True)
class Status:
    """Content: a named bundle of modifiers a status contributes while active."""

    id: str
    name: str
    modifiers: tuple[StatModifier, ...] = field(default=())


def castable(state: WorldState, caster: EntityId) -> tuple[Ability, ...]:
    """The caster's abilities whose requirements are currently met."""
    actor = state.entity(caster).actor
    if actor is None:
        return ()
    found = []
    for ability_id in sorted(actor.abilities):
        ability = state.ability_defs[ability_id]
        if ability.requires_stat is not None:
            stat, minimum = ability.requires_stat
            if derive(state, caster, stat).value < minimum:
                continue
        found.append(ability)
    return tuple(found)


def cast_events(
    state: WorldState,
    caster: EntityId,
    ability_id: str,
    target: EntityId,
    foes: tuple[EntityId, ...],
    rng: Rng,
) -> tuple[tuple[Event, ...], Rng]:
    """Resolve one cast: pairing check, then the primitive chain in order.

    A mismatched ability/target pairing is a refusal by the world — the
    grammar advertised both halves independently (design 0004 §2) — so it
    spends the turn and answers with ``CastFizzled``.
    """
    from glyphwright.effects.primitives import PRIMITIVES
    from glyphwright.kernel.state import fold

    ability = state.ability_defs[ability_id]
    turn = TurnAdvanced(turn=state.turn + 1)

    valid = target == caster if ability.targeting == TARGET_SELF else target in foes
    if not valid:
        return (
            CastFizzled(
                caster=caster,
                ability=ability_id,
                target=target,
                reason="bad_target",
            ),
            turn,
        ), rng

    events: list[Event] = []
    for name, params in ability.effects:
        primitive = PRIMITIVES[name]
        merged = {**params, "ability": ability_id}
        produced, rng = primitive(state, caster, target, merged, rng)
        events.extend(produced)
        state = fold(state, produced)
        if target != caster and target not in state.entities:
            break  # the target died mid-chain; later effects have no subject
    events.append(turn)
    return tuple(events), rng
