"""The shared turn scheduler: AI actors act inside ``step``.

After the player's command resolves, the scheduler grants turns to
AI-controlled actors until control returns to the player (design 0003 section
5.5, ADR-004). In exploration the "queue" is the activity list: every hostile
AI actor in the player's area, in sorted-id order. Battle will configure this
same scheduler with an initiative queue rather than owning a private loop.

AI decisions read only world state and the injected RNG, so NPC behavior
replays exactly.
"""

from __future__ import annotations

from collections import deque

from glyphwright.effects.combat import (
    hostile_actors,
    melee_adjacent,
    provoke,
    roll_initiative,
    strike,
)
from glyphwright.kernel.events import (
    PLAYER_DEFEATED,
    Event,
    ModePushed,
    Moved,
    aggro_flag,
)
from glyphwright.kernel.rng import Rng
from glyphwright.kernel.state import (
    MODE_BATTLE,
    MODE_EXPLORATION,
    PLAYER,
    WorldState,
    fold,
)
from glyphwright.world.entities import Entity
from glyphwright.world.space import EntityId, PosId, Space


def _distances(
    space: Space, state: WorldState, goal: PosId, mover: str
) -> dict[PosId, int]:
    """Breadth-first distances to ``goal`` over traversable terrain.

    Occupancy does not sever the graph — a body in a doorway should not
    convince a pursuer the target is unreachable — but walls and edges do.
    Geometry stays behind the Space protocol, so this works unchanged for
    room graphs.
    """
    found = {goal: 0}
    frontier = deque([goal])
    while frontier:
        pos = frontier.popleft()
        for neighbour in space.exits(pos).values():
            if neighbour in found:
                continue
            reason = space.blocked_reason(state, neighbour, mover)
            if reason is not None and reason != "occupied":
                continue
            found[neighbour] = found[pos] + 1
            frontier.append(neighbour)
    return found


def _chase_step(
    space: Space, state: WorldState, mover: Entity, target: PosId
) -> Event | None:
    at = mover.at()
    if at is None:
        return None
    distances = _distances(space, state, target, mover.id)
    current = distances.get(at)
    if current is None:
        return None
    best: tuple[int, str, PosId] | None = None
    for token, destination in sorted(space.exits(at).items()):
        if destination not in distances:
            continue
        if not space.passable(state, destination, mover.id):
            continue
        if best is None or distances[destination] < best[0]:
            best = (distances[destination], token, destination)
    if best is None or best[0] >= current:
        return None
    return Moved(actor=mover.id, origin=at, destination=best[2], exit=best[1])


def escape_step(
    state: WorldState, mover_id: EntityId, foes: tuple[EntityId, ...]
) -> Event | None:
    """One step away from danger: the passable exit maximizing the distance to
    the nearest foe, ties by token order. ``None`` when cornered."""
    mover = state.entity(mover_id)
    at = mover.at()
    if at is None:
        return None
    space = state.areas[at.area]
    foe_positions = [
        foe_at
        for foe in foes
        if foe in state.entities and (foe_at := state.entity(foe).at()) is not None
    ]
    best: tuple[int, str, PosId] | None = None
    for token, destination in sorted(space.exits(at).items()):
        if not space.passable(state, destination, mover_id):
            continue
        nearest = min(
            (
                _distances(space, state, foe_at, mover_id).get(destination, 10**9)
                for foe_at in foe_positions
            ),
            default=10**9,
        )
        if best is None or nearest > best[0]:
            best = (nearest, token, destination)
    if best is None:
        return None
    return Moved(actor=mover_id, origin=at, destination=best[2], exit=best[1])


def _engage(
    state: WorldState, entity: Entity, rng: Rng
) -> tuple[tuple[Event, ...], Rng]:
    """A formal opponent opens a battle instead of trading skirmish blows."""
    order, rng = roll_initiative(state, (PLAYER, entity.id), rng)
    return (ModePushed(mode=MODE_BATTLE, initiative=order),), rng


def _act(state: WorldState, entity: Entity, rng: Rng) -> tuple[tuple[Event, ...], Rng]:
    """One AI actor's turn: wake if provoked, then fight or give chase."""
    player_at = state.entity(PLAYER).at()
    at = entity.at()
    if player_at is None or at is None or at.area != player_at.area:
        return (), rng
    space = state.areas[at.area]
    adjacent = melee_adjacent(space, at, player_at)

    aggroed = bool(state.flags.get(aggro_flag(entity.id)))
    if not aggroed and not adjacent:
        return (), rng

    events: list[Event] = []
    if not aggroed:
        events.extend(provoke(state, entity.id))
        state = fold(state, tuple(events))

    if adjacent:
        assert entity.ai is not None
        if entity.ai.engages:
            engaged, rng = _engage(state, entity, rng)
            events.extend(engaged)
        else:
            struck, rng = strike(state, entity.id, PLAYER, rng)
            events.extend(struck)
    else:
        moved = _chase_step(space, state, entity, player_at)
        if moved is not None:
            events.append(moved)
    return tuple(events), rng


def _run_battle(
    state: WorldState, rng: Rng
) -> tuple[tuple[Event, ...], WorldState, Rng]:
    """Battle configures the same scheduler with the initiative queue."""
    events: list[Event] = []
    for combatant in state.initiative:
        if combatant == PLAYER or combatant not in state.entities:
            continue
        if state.flags.get(PLAYER_DEFEATED):
            break
        struck, rng = strike(state, combatant, PLAYER, rng)
        events.extend(struck)
        state = fold(state, struck)
    return tuple(events), state, rng


def run(state: WorldState, rng: Rng) -> tuple[tuple[Event, ...], WorldState, Rng]:
    """Grant every due AI actor its turn, folding as it goes.

    Later actors see the effects of earlier ones, and everything stops the
    moment the player is defeated or the mode changes (an engagement hands the
    rest of the round to the battle). Returns the folded state alongside the
    events so the caller does not fold them a second time.
    """
    if state.mode == MODE_BATTLE:
        return _run_battle(state, rng)
    if state.mode != MODE_EXPLORATION:
        return (), state, rng

    events: list[Event] = []
    for actor in hostile_actors(state):
        if state.flags.get(PLAYER_DEFEATED) or state.mode != MODE_EXPLORATION:
            break
        if actor.id not in state.entities:
            continue
        acted, rng = _act(state, state.entity(actor.id), rng)
        events.extend(acted)
        state = fold(state, acted)
    return tuple(events), state, rng
