"""The stat pipeline: base -> additive -> multiplicative -> clamps.

Every contribution carries provenance — which source moved the number, by how
much, and what the running value became — so "why is attack 8?" is an
assertable, self-documenting fact rather than a debugging session (design 0003
section 9.1). Equipment is the only modifier source in slice 2; statuses, perks,
and terrain join the same pipeline later.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from glyphwright.world.entities import StatModifier
from glyphwright.world.space import EntityId

if TYPE_CHECKING:
    from glyphwright.kernel.state import WorldState


@dataclass(frozen=True, slots=True)
class Contribution:
    """One provenance-carrying step of a derivation.

    ``op`` is ``base``, ``add``, ``mul``, or ``clamp``; ``running`` is the
    stat's value after this contribution applied.
    """

    source: str
    op: str
    value: int
    running: int

    def describe(self) -> str:
        match self.op:
            case "base":
                return f"base {self.value}"
            case "add":
                return f"{self.value:+d} {self.source}"
            case "mul":
                return f"x{self.value}% {self.source}"
            case _:
                return f"clamped to {self.running}"


@dataclass(frozen=True, slots=True)
class Derivation:
    """A stat's value together with the full chain that produced it."""

    stat: str
    value: int
    contributions: tuple[Contribution, ...]

    def explain(self) -> tuple[str, ...]:
        header = f"{self.stat} = {self.value}"
        return (header, *(c.describe() for c in self.contributions))


def _equipped_modifiers(
    state: WorldState, entity_id: EntityId, stat: str
) -> tuple[tuple[str, StatModifier], ...]:
    """Modifiers from worn equipment, with their provenance labels.

    Slots iterate in sorted order and modifiers in authored order, the same
    determinism rule as entity iteration (0003 section 5.4).
    """
    equipment = state.entity(entity_id).equipment
    if equipment is None:
        return ()
    found: list[tuple[str, StatModifier]] = []
    for slot, item_id in equipment.slots:
        equippable = state.entity(item_id).equippable
        if equippable is None:
            continue
        source = f"{item_id} (equipped {slot})"
        found.extend(
            (source, modifier)
            for modifier in equippable.modifiers
            if modifier.stat == stat
        )
    return tuple(found)


def derive(state: WorldState, entity_id: EntityId, stat: str) -> Derivation:
    """Resolve one stat through the ordered pipeline."""
    actor = state.entity(entity_id).actor
    base = actor.base_stat(stat) if actor is not None else 0
    running = base
    contributions = [Contribution(source="base", op="base", value=base, running=base)]

    modifiers = _equipped_modifiers(state, entity_id, stat)
    for source, modifier in modifiers:
        if modifier.op != "add":
            continue
        running += modifier.value
        contributions.append(
            Contribution(source=source, op="add", value=modifier.value, running=running)
        )
    for source, modifier in modifiers:
        if modifier.op != "mul":
            continue
        running = running * modifier.value // 100
        contributions.append(
            Contribution(source=source, op="mul", value=modifier.value, running=running)
        )

    clamped = max(running, 0)
    if clamped != running:
        contributions.append(
            Contribution(source="engine", op="clamp", value=0, running=clamped)
        )
    return Derivation(stat=stat, value=clamped, contributions=tuple(contributions))
