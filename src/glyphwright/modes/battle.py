"""Menu battle: a JRPG-style fight as an ordinary mode (design 0003 §10.1).

Battle is not a special case: it is pushed on the mode stack by an engaging
hostile, configures the shared scheduler with the initiative queue rolled at
push (ADR-004), and pops with an outcome the mode beneath consumes. Distance
is abstracted away — combatants are simply in the fight — which is what makes
this the menu presentation; the tactics presentation reuses ``GridSpace``
later.
"""

from __future__ import annotations

from glyphwright.effects.combat import hostile_actors, melee_adjacent, strike
from glyphwright.frames.frame import ActorSummary, MenuView, PromptSpec, SemanticFrame
from glyphwright.kernel.commands import (
    Attack,
    Cast,
    Command,
    CommandGrammar,
    Flee,
    Look,
    Use,
)
from glyphwright.kernel.events import (
    Event,
    FleeFailed,
    ModePopped,
    TurnAdvanced,
)
from glyphwright.kernel.rng import Rng
from glyphwright.kernel.scheduler import escape_step
from glyphwright.kernel.state import MODE_BATTLE, PLAYER, WorldState
from glyphwright.modes import common, messages

NAME = MODE_BATTLE

VERBS = frozenset({"attack", "use", "flee", "look", "cast"})


def _foes(state: WorldState) -> tuple[str, ...]:
    """Living opponents on the initiative list, in sorted-id order."""
    return tuple(
        sorted(
            combatant
            for combatant in state.initiative
            if combatant != PLAYER and combatant in state.entities
        )
    )


def available_commands(state: WorldState) -> CommandGrammar:
    verbs: list[tuple[str, tuple[tuple[str, ...], ...]]] = []
    foes = _foes(state)
    if foes:
        verbs.append(("attack", (foes,)))
    usable = common.usable_items(state)
    if usable:
        verbs.append(("use", (usable,)))
    cast_domains = common.cast_grammar(state, foes)
    if cast_domains is not None:
        verbs.append(("cast", cast_domains))
    verbs.append(("flee", ()))
    verbs.append(("look", ()))
    return CommandGrammar(verbs=tuple(verbs))


def handle(
    state: WorldState, command: Command, rng: Rng
) -> tuple[tuple[Event, ...], Rng]:
    match command:
        case Look():
            return (), rng
        case Use(item=item_id):
            return common.use_item(state, item_id), rng
        case Attack(target=target_id):
            struck, rng = strike(state, PLAYER, target_id, rng)
            return (*struck, TurnAdvanced(turn=state.turn + 1)), rng
        case Cast(ability=ability_id, target=target_id):
            from glyphwright.effects.abilities import cast_events

            return cast_events(state, PLAYER, ability_id, target_id, _foes(state), rng)
        case Flee():
            return _flee(state), rng
        case _:
            raise ValueError(f"battle cannot handle {command.verb!r}")


def _flee(state: WorldState) -> tuple[Event, ...]:
    """Break away: pop the battle and gain ground, or fail and pay the turn.

    The escape is scored against every hostile in the area, not only the
    battle's foes, and it only counts as an escape if it actually breaks
    melee contact with the foes — otherwise the same step would re-engage
    and "You break away and flee!" would be a lie.
    """
    turn = TurnAdvanced(turn=state.turn + 1)
    threats = tuple(actor.id for actor in hostile_actors(state))
    moved = escape_step(state, PLAYER, threats)
    if moved is None:
        return (FleeFailed(actor=PLAYER), turn)
    space = state.areas[moved.destination.area]
    still_in_reach = any(
        (foe_at := state.entity(foe).at()) is not None
        and melee_adjacent(space, moved.destination, foe_at)
        for foe in _foes(state)
    )
    if still_in_reach:
        return (FleeFailed(actor=PLAYER), turn)
    return (ModePopped(mode=NAME, outcome="fled"), moved, turn)


def view(state: WorldState, events: tuple[Event, ...]) -> SemanticFrame:
    player_at = state.entity(PLAYER).at()
    assert player_at is not None
    combatants = tuple(c for c in state.initiative if c in state.entities)
    return SemanticFrame(
        turn=state.turn,
        mode=NAME,
        viewport=MenuView(area=player_at.area, combatants=combatants),
        actors=_actors(state, combatants),
        messages=tuple(
            message for event in events if (message := messages.describe(event))
        ),
        prompt=PromptSpec(kind="command"),
        commands=available_commands(state),
    )


def _actors(state: WorldState, combatants: tuple[str, ...]) -> tuple[ActorSummary, ...]:
    summaries = []
    for combatant in combatants:
        entity = state.entity(combatant)
        at = entity.at()
        if entity.actor is None or at is None:
            continue
        summaries.append(
            ActorSummary(
                id=entity.id,
                name=entity.actor.name,
                hp=entity.actor.hp,
                max_hp=entity.actor.max_hp,
                at=at,
                statuses=entity.statuses.ids() if entity.statuses else (),
            )
        )
    return tuple(summaries)
