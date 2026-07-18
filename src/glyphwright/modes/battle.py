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
from glyphwright.frames.frame import (
    ActorSummary,
    MenuView,
    PromptSpec,
    SemanticFrame,
    Viewport,
)
from glyphwright.kernel.commands import (
    Attack,
    Cast,
    Command,
    CommandGrammar,
    Flee,
    Look,
    Move,
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
from glyphwright.kernel.scheduler import battle_homecoming, escape_step
from glyphwright.kernel.state import MODE_BATTLE, PLAYER, WorldState, fold
from glyphwright.modes import common, messages
from glyphwright.world.grid import GridSpace
from glyphwright.world.space import PosId

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


def _melee_foes(state: WorldState) -> tuple[str, ...]:
    """In the arena, steel needs adjacency; the menu abstracts distance."""
    foes = _foes(state)
    if not state.battle_returns:
        return foes
    player_at = state.entity(PLAYER).at()
    if player_at is None:
        return ()
    space = state.areas[player_at.area]
    return tuple(
        foe
        for foe in foes
        if (at := state.entity(foe).at()) is not None
        and at.area == player_at.area
        and melee_adjacent(space, player_at, at)
    )


def available_commands(state: WorldState) -> CommandGrammar:
    verbs: list[tuple[str, tuple[tuple[str, ...], ...]]] = []
    if state.battle_returns:
        player_at = state.entity(PLAYER).at()
        assert player_at is not None
        exits = tuple(sorted(state.exits_from(player_at)))
        if exits:
            verbs.append(("move", (exits,)))
    melee = _melee_foes(state)
    if melee:
        verbs.append(("attack", (melee,)))
    usable = common.usable_items(state)
    if usable:
        verbs.append(("use", (usable,)))
    # Steel needs adjacency; magic outranges it and reaches any living foe
    # (design 0006 §2).
    cast_domains = common.cast_grammar(state, _foes(state))
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
        case Move(exit=token):
            return common.move_player(state, token), rng
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

    Both presentations obey the same break-contact rule (design 0006 §2): the
    escaping step is scored against every hostile in reach, and it only counts
    if it breaks melee contact with the battle's foes — otherwise the same
    step would re-engage and "You break away and flee!" would be a lie. In an
    arena battle everyone first goes home, and the escape is judged from the
    homecoming tile.
    """
    turn = TurnAdvanced(turn=state.turn + 1)
    prologue: tuple[Event, ...] = ()
    landed = state
    if state.battle_returns:
        prologue = battle_homecoming(state)
        landed = fold(state, prologue)
    escape = _escaping_step(landed)
    if escape is None:
        return (FleeFailed(actor=PLAYER), turn)
    return (*prologue, ModePopped(mode=NAME, outcome="fled"), escape, turn)


def _escaping_step(state: WorldState) -> Moved | None:
    """The player's one escaping step, or ``None`` when no step breaks melee
    contact with the battle's foes."""
    threats = tuple(actor.id for actor in hostile_actors(state))
    moved = escape_step(state, PLAYER, threats)
    if moved is None:
        return None
    space = state.areas[moved.destination.area]
    still_in_reach = any(
        (foe_at := state.entity(foe).at()) is not None
        and foe_at.area == moved.destination.area
        and melee_adjacent(space, moved.destination, foe_at)
        for foe in _foes(state)
    )
    return None if still_in_reach else moved


def view(state: WorldState, events: tuple[Event, ...]) -> SemanticFrame:
    """Project the battle into the canonical observation.

    In a fov-active arena the one visible set filters the viewport, the actor
    summaries, and the messages alike, exactly as exploration does — a frame
    must not narrate or list a foe its viewport conceals (design 0006 §1). The
    menu presentation abstracts distance, so it never conceals a combatant.
    """
    player_at = state.entity(PLAYER).at()
    assert player_at is not None
    combatants = tuple(c for c in state.initiative if c in state.entities)
    sight: frozenset[PosId] | None = None
    viewport: Viewport = MenuView(area=player_at.area, combatants=combatants)
    if state.battle_returns:
        space = state.areas[player_at.area]
        assert isinstance(space, GridSpace)
        sight = common.player_sight(state)
        viewport = common.grid_viewport(state, space, sight)
    return SemanticFrame(
        turn=state.turn,
        mode=NAME,
        viewport=viewport,
        actors=_actors(state, combatants, sight),
        messages=tuple(
            message
            for event in events
            if common.witnessed(event, sight) and (message := messages.describe(event))
        ),
        prompt=PromptSpec(kind="command"),
        commands=available_commands(state),
    )


def _actors(
    state: WorldState, combatants: tuple[str, ...], sight: frozenset[PosId] | None
) -> tuple[ActorSummary, ...]:
    summaries = []
    for combatant in combatants:
        entity = state.entity(combatant)
        at = entity.at()
        if entity.actor is None or at is None:
            continue
        if sight is not None and combatant != PLAYER and at not in sight:
            continue  # beyond the light
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
