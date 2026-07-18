"""Status and perk hooks: event-triggered effects (design 0007 §1).

Hooks fire inside ``step``, in the scheduler epilogue: the pass walks the
whole round's events in order and executes each triggered hook's effect chain
on the holder. Triggers and conditions are evaluated against the state *as of
the triggering event* — replayed forward from the round's opening state — so
a status applied later in the round never fires retroactively, and an
``hp_below`` gate reads the hp the holder actually had when the event
happened. The effects themselves execute against the round's final state and
are ordinary primitive events, appended to the log and folded, so triggered
effects replay exactly (0003 §9.3). Events produced by hooks do not trigger
further hooks within the same step — one generation, which closes the
recursion question by construction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from glyphwright.effects.abilities import Hook, bearing_ids, run_effect_chain
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
    for status_id in (
        *bearing_ids(entity, "statuses"),
        *bearing_ids(entity, "perks"),
    ):
        if status_id in seen:
            continue
        seen.add(status_id)
        definition = state.status_defs.get(status_id)
        if definition is None:
            continue
        found.extend((status_id, hook) for hook in definition.hooks)
    return tuple(found)


def _triggered(state: WorldState, event: Event) -> tuple[str, tuple[EntityId, ...]]:
    """The trigger an event raises and whose hooks it can fire, together so
    the pairing cannot drift: the victim of damage, every bearer at the close
    of a turn."""
    match event:
        case DamageDealt():
            return "damage_taken", (event.target,)
        case TurnAdvanced():
            return "turn_end", tuple(
                sorted(
                    entity.id
                    for entity in state.entities.values()
                    if (entity.statuses is not None and entity.statuses.active)
                    or (entity.actor is not None and entity.actor.perks)
                )
            )
        case _:
            return "", ()


def _condition_met(state: WorldState, holder: EntityId, hook: Hook) -> bool:
    if hook.hp_below is None:
        return True
    actor = state.entity(holder).actor
    if actor is None:
        return False
    return actor.hp * 100 < actor.max_hp * hook.hp_below


def hook_events(
    opening: WorldState,
    state: WorldState,
    round_events: tuple[Event, ...],
    rng: Rng,
) -> tuple[tuple[Event, ...], WorldState, Rng]:
    """Fire every hook the round's events trigger, folding as it goes.

    ``opening`` is the state before any of ``round_events`` folded; the pass
    replays them one at a time so each trigger sees its own moment. Effects
    are self-directed (source and target are the holder), labelled with the
    status id through the reserved ``ability`` param, and run against the
    accumulated ``state``. A holder that has since died is skipped.
    """
    from glyphwright.kernel.state import apply

    produced: list[Event] = []
    at_event = opening
    for event in round_events:
        at_event = apply(at_event, event)
        trigger, holders = _triggered(at_event, event)
        if not trigger:
            continue
        for holder in holders:
            if holder not in state.entities:
                continue
            for status_id, hook in _bearings(at_event, holder):
                if hook.on != trigger or not _condition_met(at_event, holder, hook):
                    continue
                out, state, rng = run_effect_chain(
                    state,
                    holder,
                    holder,
                    status_id,
                    hook.effects,
                    rng,
                    pending_turn=False,
                )
                produced.extend(out)
    return tuple(produced), state, rng
