"""Status and perk hooks: event-triggered effects (design 0007 §1).

Hooks fire inside ``step``, in the scheduler epilogue: the pass scans the
whole round's events in order and executes each triggered hook's effect chain
on the holder. Consequent events are ordinary primitive events, appended to
the log and folded, so triggered effects replay exactly (0003 §9.3). Events
produced by hooks do not trigger further hooks within the same step — one
generation, which closes the recursion question by construction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from glyphwright.effects.abilities import Hook
from glyphwright.kernel.events import DamageDealt, Event, TurnAdvanced
from glyphwright.kernel.rng import Rng
from glyphwright.world.space import EntityId

if TYPE_CHECKING:
    from glyphwright.kernel.state import WorldState


def _bearings(state: WorldState, holder: EntityId) -> tuple[tuple[str, Hook], ...]:
    """The holder's hooks in firing order: statuses before perks, each sorted
    by id; an id borne both ways fires once."""
    entity = state.entity(holder)
    seen: set[str] = set()
    found: list[tuple[str, Hook]] = []
    ids: list[str] = []
    if entity.statuses is not None:
        ids.extend(status_id for status_id, _ in sorted(entity.statuses.active))
    if entity.actor is not None:
        ids.extend(sorted(entity.actor.perks))
    for status_id in ids:
        if status_id in seen:
            continue
        seen.add(status_id)
        definition = state.status_defs.get(status_id)
        if definition is None:
            continue
        found.extend((status_id, hook) for hook in definition.hooks)
    return tuple(found)


def _holders(state: WorldState, event: Event) -> tuple[EntityId, ...]:
    """Whose hooks an event can trigger: the victim of damage, everyone at
    the close of a turn."""
    match event:
        case DamageDealt():
            return (event.target,)
        case TurnAdvanced():
            return tuple(sorted(state.entities))
        case _:
            return ()


def _trigger(event: Event) -> str:
    match event:
        case DamageDealt():
            return "damage_taken"
        case TurnAdvanced():
            return "turn_end"
        case _:
            return ""


def _condition_met(state: WorldState, holder: EntityId, hook: Hook) -> bool:
    if hook.hp_below is None:
        return True
    actor = state.entity(holder).actor
    if actor is None:
        return False
    return actor.hp * 100 < actor.max_hp * hook.hp_below


def hook_events(
    state: WorldState, round_events: tuple[Event, ...], rng: Rng
) -> tuple[tuple[Event, ...], WorldState, Rng]:
    """Fire every hook the round's events trigger, folding as it goes.

    Effects are self-directed (source and target are the holder) and labelled
    with the status id through the reserved ``ability`` param. A holder that
    died earlier in the pass is skipped.
    """
    from glyphwright.effects.primitives import PRIMITIVES
    from glyphwright.kernel.state import fold

    produced: list[Event] = []
    for event in round_events:
        trigger = _trigger(event)
        if not trigger:
            continue
        for holder in _holders(state, event):
            if holder not in state.entities:
                continue
            for status_id, hook in _bearings(state, holder):
                if hook.on != trigger or not _condition_met(state, holder, hook):
                    continue
                for name, params in hook.effects:
                    if holder not in state.entities:
                        break  # the holder died mid-chain
                    merged = {**params, "ability": status_id}
                    out, rng = PRIMITIVES[name](state, holder, holder, merged, rng)
                    produced.extend(out)
                    state = fold(state, out)
    return tuple(produced), state, rng
