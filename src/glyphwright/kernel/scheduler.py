"""The turn scheduler: computer-controlled actors act inside ``step``.

After the player's command resolves, the scheduler grants every due actor its
turn, folding as it goes, before the turn closes. Outside a battle the queue
is every hostile in the world, in id order. It is not filtered by area: an
aggroed hostile in another area chases the player through portals (v0
finding K8: v0's docstring said the queue was area-filtered). In a battle the
queue is the initiative order.

Every decision reads only world state and the injected RNG, so foes replay
exactly.
"""

from __future__ import annotations

from collections import deque

from glyphwright.effects.combat import (
    hostile_actors,
    melee_adjacent,
    roll_initiative,
    strike,
)
from glyphwright.kernel.events import Event, ModePopped, ModePushed, Moved, Provoked
from glyphwright.kernel.rng import Rng
from glyphwright.kernel.state import MODE_BATTLE, PLAYER, WorldState, fold
from glyphwright.world.entities import Entity
from glyphwright.world.space import EntityId, PosId

_FAR = 10**9


def _traversable(state: WorldState, pos: PosId, mover: EntityId) -> bool:
    reason = state.areas[pos.area].blocked_reason(state, pos, mover)
    return reason is None or reason == "occupied"


def _distances(state: WorldState, goal: PosId, mover: EntityId) -> dict[PosId, int]:
    """Breadth-first step counts to ``goal`` over the movement graph.

    The graph is ``state.exits_from``, space exits plus portals, so pursuit
    crosses areas exactly where the player can. A body in a doorway does not
    sever the graph, but walls and edges do.
    """
    found = {goal: 0}
    frontier = deque([goal])
    while frontier:
        pos = frontier.popleft()
        for neighbour in state.exits_from(pos).values():
            if neighbour in found or not _traversable(state, neighbour, mover):
                continue
            found[neighbour] = found[pos] + 1
            frontier.append(neighbour)
    return found


def _passable(state: WorldState, pos: PosId, mover: EntityId) -> bool:
    return state.areas[pos.area].passable(state, pos, mover)


def _chase_step(state: WorldState, mover: Entity, target: PosId) -> Moved | None:
    """One step that brings ``mover`` closer to ``target``, ties by token."""
    at = mover.at()
    if at is None:
        return None
    distances = _distances(state, target, mover.id)
    current = distances.get(at)
    if current is None:
        return None
    best: tuple[int, str, PosId] | None = None
    for token, destination in sorted(state.exits_from(at).items()):
        if destination not in distances or not _passable(state, destination, mover.id):
            continue
        if best is None or distances[destination] < best[0]:
            best = (distances[destination], token, destination)
    if best is None or best[0] >= current:
        return None
    return Moved(actor=mover.id, origin=at, destination=best[2], exit=best[1])


def escape_step(
    state: WorldState, mover_id: EntityId, foes: tuple[EntityId, ...]
) -> Moved | None:
    """The passable step that ends farthest from the nearest foe, ties by
    token; ``None`` when there is no passable step at all."""
    at = state.entity(mover_id).at()
    if at is None:
        return None
    foe_distances = [
        _distances(state, foe_at, mover_id)
        for foe in foes
        if foe in state.entities and (foe_at := state.entity(foe).at()) is not None
    ]
    best: tuple[int, str, PosId] | None = None
    for token, destination in sorted(state.exits_from(at).items()):
        if not _passable(state, destination, mover_id):
            continue
        nearest = min(
            (distances.get(destination, _FAR) for distances in foe_distances),
            default=_FAR,
        )
        if best is None or nearest > best[0]:
            best = (nearest, token, destination)
    if best is None:
        return None
    return Moved(actor=mover_id, origin=at, destination=best[2], exit=best[1])


def _joiners(state: WorldState, engager: Entity) -> tuple[EntityId, ...]:
    """Who a battle draws in: the engager, plus every hostile in the player's
    area that is already aggroed or within reach of the player."""
    player_at = state.entity(PLAYER).at()
    assert player_at is not None
    joiners = {engager.id}
    for hostile in hostile_actors(state):
        at = hostile.at()
        if at is None or at.area != player_at.area:
            continue
        assert hostile.ai is not None
        if hostile.ai.aggroed or melee_adjacent(state, at, player_at):
            joiners.add(hostile.id)
    return tuple(sorted(joiners))


def _engage(
    state: WorldState, engager: Entity, rng: Rng
) -> tuple[tuple[Event, ...], Rng]:
    """Start a battle: roll initiative, then let every foe that outrolled the
    player strike first. That is what makes the advertised order real."""
    foes = _joiners(state, engager)
    order, rng = roll_initiative(state, (PLAYER, *foes), rng)
    events: list[Event] = [
        Provoked(actor=foe)
        for foe in foes
        if (ai := state.entity(foe).ai) is not None and not ai.aggroed
    ]
    events.append(ModePushed(mode=MODE_BATTLE, initiative=order))
    state = fold(state, tuple(events))
    for combatant in order:
        if combatant == PLAYER or state.defeated:
            break
        struck, rng = strike(state, combatant, PLAYER, rng)
        events.extend(struck)
        state = fold(state, struck)
    return tuple(events), rng


def _act(state: WorldState, hostile: Entity, rng: Rng) -> tuple[tuple[Event, ...], Rng]:
    """One hostile's turn outside a battle: wake when the player is within
    reach, start a battle on contact, and otherwise chase once awake."""
    player_at = state.entity(PLAYER).at()
    at = hostile.at()
    assert hostile.ai is not None
    if player_at is None or at is None:
        return (), rng
    adjacent = melee_adjacent(state, at, player_at)
    if adjacent:
        return _engage(state, hostile, rng)
    if not hostile.ai.aggroed:
        return (), rng
    moved = _chase_step(state, hostile, player_at)
    return ((moved,) if moved is not None else ()), rng


def _queue(state: WorldState) -> tuple[EntityId, ...]:
    if state.mode == MODE_BATTLE:
        return tuple(c for c in state.initiative if c != PLAYER)
    return tuple(hostile.id for hostile in hostile_actors(state))


def _outcome(state: WorldState) -> tuple[Event, ...]:
    """Victory or defeat ends a battle."""
    if state.mode != MODE_BATTLE:
        return ()
    if state.defeated:
        return (ModePopped(mode=MODE_BATTLE, outcome="defeat"),)
    if not any(c != PLAYER and c in state.entities for c in state.initiative):
        return (ModePopped(mode=MODE_BATTLE, outcome="victory"),)
    return ()


def run(state: WorldState, rng: Rng) -> tuple[tuple[Event, ...], WorldState, Rng]:
    """Grant every due actor its turn, then end a finished battle.

    ``state`` already holds the player's half of the round. Later actors see
    what earlier ones did. The round stops when the player is defeated or the
    mode changes: a hostile that starts a battle hands the rest of the round
    to it. Returns the folded state with the events, so the caller does not
    fold them again.
    """
    opening_mode = state.mode
    events: list[Event] = []
    for actor_id in _queue(state):
        if state.defeated or state.mode != opening_mode:
            break
        if actor_id not in state.entities:
            continue
        if state.mode == MODE_BATTLE:
            acted, rng = strike(state, actor_id, PLAYER, rng)
        else:
            acted, rng = _act(state, state.entity(actor_id), rng)
        events.extend(acted)
        state = fold(state, acted)
    outcome = _outcome(state)
    events.extend(outcome)
    return tuple(events), fold(state, outcome), rng
