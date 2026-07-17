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
    strike,
)
from glyphwright.kernel.events import PLAYER_DEFEATED, Event, Moved, aggro_flag
from glyphwright.kernel.rng import Rng
from glyphwright.kernel.state import PLAYER, WorldState, fold
from glyphwright.world.entities import Entity
from glyphwright.world.space import PosId, Space


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
        struck, rng = strike(state, entity.id, PLAYER, rng)
        events.extend(struck)
    else:
        moved = _chase_step(space, state, entity, player_at)
        if moved is not None:
            events.append(moved)
    return tuple(events), rng


def run(state: WorldState, rng: Rng) -> tuple[tuple[Event, ...], WorldState, Rng]:
    """Grant every due AI actor its turn, folding as it goes.

    Later actors see the effects of earlier ones, and everything stops the
    moment the player is defeated. Returns the folded state alongside the
    events so the caller does not fold them a second time.
    """
    events: list[Event] = []
    for actor in hostile_actors(state):
        if state.flags.get(PLAYER_DEFEATED):
            break
        if actor.id not in state.entities:
            continue
        acted, rng = _act(state, state.entity(actor.id), rng)
        events.extend(acted)
        state = fold(state, acted)
    return tuple(events), state, rng
