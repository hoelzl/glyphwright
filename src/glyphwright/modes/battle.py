"""Menu battle: a fight as an ordinary mode on the mode stack.

A hostile that reaches the player pushes the battle, with the initiative
order rolled at the push. The scheduler serves that order, and a battle ends
in victory, defeat, or a successful flee. Distance is abstracted away:
combatants are simply in the fight, which is what makes this a menu battle.
"""

from __future__ import annotations

from glyphwright.effects.combat import hostile_actors, melee_adjacent, strike
from glyphwright.frames.frame import ActorSummary, MenuView, PromptSpec, SemanticFrame
from glyphwright.kernel.commands import (
    Attack,
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
    Moved,
    TurnAdvanced,
)
from glyphwright.kernel.rng import Rng
from glyphwright.kernel.scheduler import escape_step
from glyphwright.kernel.state import MODE_BATTLE, PLAYER, WorldState
from glyphwright.modes import common, messages

NAME = MODE_BATTLE

VERBS = frozenset({"attack", "use", "flee", "look"})


def _foes(state: WorldState) -> tuple[str, ...]:
    """Living opponents on the initiative list, in id order."""
    return tuple(
        sorted(c for c in state.initiative if c != PLAYER and c in state.entities)
    )


def available_commands(state: WorldState) -> CommandGrammar:
    verbs: list[tuple[str, tuple[tuple[str, ...], ...]]] = []
    foes = _foes(state)
    if foes:
        verbs.append(("attack", (foes,)))
    usable = common.usable_items(state)
    if usable:
        verbs.append(("use", (usable,)))
    verbs.extend((("flee", ()), ("look", ())))
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
        case Flee():
            return _flee(state), rng
        case _:
            raise ValueError(f"battle cannot handle {command.verb!r}")


def _flee(state: WorldState) -> tuple[Event, ...]:
    """Break away and take one step, or fail and pay the turn.

    The step only counts if it breaks melee contact with every foe of the
    battle; otherwise "You break away and flee!" would be a lie.
    """
    turn = TurnAdvanced(turn=state.turn + 1)
    escape = _escaping_step(state)
    if escape is None:
        return (FleeFailed(actor=PLAYER), turn)
    return (ModePopped(mode=NAME, outcome="fled"), escape, turn)


def _escaping_step(state: WorldState) -> Moved | None:
    threats = tuple(hostile.id for hostile in hostile_actors(state))
    moved = escape_step(state, PLAYER, threats)
    if moved is None:
        return None
    still_in_reach = any(
        (foe_at := state.entity(foe).at()) is not None
        and melee_adjacent(state, moved.destination, foe_at)
        for foe in _foes(state)
    )
    return None if still_in_reach else moved


def view(state: WorldState, events: tuple[Event, ...]) -> SemanticFrame:
    player_at = state.entity(PLAYER).at()
    assert player_at is not None
    combatants = tuple(c for c in state.initiative if c in state.entities)
    actors = []
    for combatant in combatants:
        entity = state.entity(combatant)
        at = entity.at()
        if entity.actor is not None and at is not None:
            actors.append(ActorSummary.of(entity, at))
    return SemanticFrame(
        turn=state.turn,
        mode=NAME,
        viewport=MenuView(area=player_at.area, combatants=combatants),
        actors=tuple(actors),
        messages=tuple(
            message for event in events if (message := messages.describe(event))
        ),
        prompt=PromptSpec(kind="command"),
        commands=available_commands(state),
        inventory=common.carried(state),
    )
