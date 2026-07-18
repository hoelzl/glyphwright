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
from glyphwright.kernel.events import CastFizzled, Event, ManaSpent, TurnAdvanced
from glyphwright.kernel.rng import Rng
from glyphwright.world.entities import Entity, StatModifier
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
    cost: int = 0

    def __post_init__(self) -> None:
        if self.targeting not in (TARGET_SELF, TARGET_FOE):
            raise ValueError(
                f"ability {self.id!r} has unknown targeting {self.targeting!r}"
            )
        if self.cost < 0:
            raise ValueError(f"ability {self.id!r} has a negative cost")


HOOK_TRIGGERS = frozenset({"damage_taken", "turn_end"})


@dataclass(frozen=True, slots=True)
class Hook:
    """Content: an event-triggered, self-directed effect chain on a status.

    ``on`` names a trigger from the closed vocabulary; ``hp_below`` (percent
    of max hp, 1–99) optionally gates the firing (design 0007 §1).
    """

    on: str
    effects: tuple[tuple[str, Mapping[str, object]], ...]
    hp_below: int | None = None

    def __post_init__(self) -> None:
        if self.on not in HOOK_TRIGGERS:
            raise ValueError(f"unknown hook trigger {self.on!r}")
        if self.hp_below is not None and not 1 <= self.hp_below <= 99:
            raise ValueError(
                f"hook hp_below must be a percent in 1..99, got {self.hp_below!r}"
            )


@dataclass(frozen=True, slots=True)
class Status:
    """Content: a named bundle of modifiers a status contributes while active,
    plus event-triggered hooks (design 0007 §1)."""

    id: str
    name: str
    modifiers: tuple[StatModifier, ...] = field(default=())
    hooks: tuple[Hook, ...] = field(default=())


def bearing_ids(entity: Entity, kind: str) -> tuple[str, ...]:
    """Sorted ids of the statuses or perks an entity bears.

    The one enumeration the stat pipeline and the hook pass share, so they
    can never disagree about what an entity carries.
    """
    if kind == "statuses":
        if entity.statuses is None:
            return ()
        return tuple(status_id for status_id, _ in sorted(entity.statuses.active))
    assert kind == "perks"
    if entity.actor is None:
        return ()
    return tuple(sorted(entity.actor.perks))


def run_effect_chain(
    state: WorldState,
    source: EntityId,
    target: EntityId,
    label: str,
    effects: tuple[tuple[str, Mapping[str, object]], ...],
    rng: Rng,
    *,
    pending_turn: bool,
) -> tuple[tuple[Event, ...], WorldState, Rng]:
    """Execute one effect chain in order, folding between steps.

    The one chain runner casts and hooks share (design 0007 §5). ``label``
    fills the reserved ``ability`` evidence param; ``pending_turn`` tells
    duration-granting primitives whether the step's turn advance is still to
    come (a player cast) or already folded (an AI cast or a hook), so a
    duration means the same thing for every caster. The chain stops when its
    subject leaves the world.
    """
    from glyphwright.effects.primitives import PRIMITIVES
    from glyphwright.kernel.state import fold

    events: list[Event] = []
    for name, params in effects:
        if target not in state.entities:
            break  # the subject died mid-chain; later effects have no subject
        merged = {**params, "ability": label, "pending_turn": pending_turn}
        produced, rng = PRIMITIVES[name](state, source, target, merged, rng)
        events.extend(produced)
        state = fold(state, produced)
    return tuple(events), state, rng


def castable(state: WorldState, caster: EntityId) -> tuple[Ability, ...]:
    """The caster's abilities whose requirements are currently met.

    Affordability is advertisement (design 0009 §2): an ability the caster
    cannot pay for is not offered — to the player's grammar or to the AI's
    pursuit — exactly like an unmet stat requirement.
    """
    actor = state.entity(caster).actor
    if actor is None:
        return ()
    found = []
    for ability_id in sorted(actor.abilities):
        ability = state.ability_defs[ability_id]
        if ability.cost > actor.mp:
            continue
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
    spend_turn: bool = True,
) -> tuple[tuple[Event, ...], Rng]:
    """Resolve one cast: pairing check, then the primitive chain in order.

    A mismatched ability/target pairing is a refusal by the world — the
    grammar advertised both halves independently (design 0004 §2) — so it
    spends the turn and answers with ``CastFizzled``. An AI cast passes
    ``spend_turn=False``: only the player's command closes a turn, and the
    AI's pairing is chosen valid so it can never fizzle.
    """
    ability = state.ability_defs[ability_id]
    turn = TurnAdvanced(turn=state.turn + 1)

    valid = target == caster if ability.targeting == TARGET_SELF else target in foes
    if not valid:
        assert spend_turn, "an AI cast must be constructed with a valid pairing"
        return (
            CastFizzled(
                caster=caster,
                ability=ability_id,
                target=target,
                reason="bad_target",
            ),
            turn,
        ), rng

    from glyphwright.kernel.state import fold

    events: list[Event] = []
    if ability.cost:
        # The cost precedes the chain; a fizzle above spent nothing (the
        # cast never resolved — the turn is the fizzle's whole price).
        spend = ManaSpent(caster=caster, amount=ability.cost)
        events.append(spend)
        state = fold(state, (spend,))
    chain, _, rng = run_effect_chain(
        state,
        caster,
        target,
        ability_id,
        ability.effects,
        rng,
        pending_turn=spend_turn,
    )
    events.extend(chain)
    if spend_turn:
        return (*events, turn), rng
    return tuple(events), rng
