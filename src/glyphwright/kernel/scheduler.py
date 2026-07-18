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

from glyphwright.effects.abilities import TARGET_FOE, cast_events, castable
from glyphwright.effects.combat import (
    hostile_actors,
    melee_adjacent,
    provoke,
    roll_initiative,
    strike,
)
from glyphwright.effects.hooks import hook_events
from glyphwright.kernel.events import (
    PLAYER_DEFEATED,
    Event,
    ModePopped,
    ModePushed,
    Moved,
    StatusExpired,
    aggro_flag,
)
from glyphwright.kernel.rng import Rng
from glyphwright.kernel.state import (
    FOCUS_MODES,
    MODE_BATTLE,
    PLAYER,
    WorldState,
    fold,
)
from glyphwright.world.entities import Entity
from glyphwright.world.space import EntityId, PosId


def _traversable(state: WorldState, pos: PosId, mover: EntityId) -> bool:
    area = state.areas.get(pos.area)
    if area is None:
        return False
    reason = area.blocked_reason(state, pos, mover)
    return reason is None or reason == "occupied"


def _distances(state: WorldState, goal: PosId, mover: EntityId) -> dict[PosId, int]:
    """Breadth-first distances to ``goal`` over the movement graph.

    The graph is ``state.exits_from`` — space exits plus portals — so pursuit
    crosses areas exactly where the player can. Occupancy does not sever the
    graph (a body in a doorway should not convince a pursuer the target is
    unreachable), but walls and edges do. One-way exits make this an
    approximation from the goal side; determinism is unaffected, only chase
    quality on asymmetric maps.
    """
    found = {goal: 0}
    frontier = deque([goal])
    while frontier:
        pos = frontier.popleft()
        for neighbour in state.exits_from(pos).values():
            if neighbour in found:
                continue
            if not _traversable(state, neighbour, mover):
                continue
            found[neighbour] = found[pos] + 1
            frontier.append(neighbour)
    return found


def _passable(state: WorldState, pos: PosId, mover: EntityId) -> bool:
    area = state.areas.get(pos.area)
    return area is not None and area.passable(state, pos, mover)


def _chase_step(state: WorldState, mover: Entity, target: PosId) -> Event | None:
    at = mover.at()
    if at is None:
        return None
    distances = _distances(state, target, mover.id)
    current = distances.get(at)
    if current is None:
        return None
    best: tuple[int, str, PosId] | None = None
    for token, destination in sorted(state.exits_from(at).items()):
        if destination not in distances:
            continue
        if not _passable(state, destination, mover.id):
            continue
        if best is None or distances[destination] < best[0]:
            best = (distances[destination], token, destination)
    if best is None or best[0] >= current:
        return None
    return Moved(actor=mover.id, origin=at, destination=best[2], exit=best[1])


def escape_step(
    state: WorldState, mover_id: EntityId, foes: tuple[EntityId, ...]
) -> Moved | None:
    """One step away from danger: the passable exit maximizing the distance to
    the nearest foe, ties by token order. ``None`` when cornered. Distances
    run over the same cross-area movement graph pursuit uses, so foes in
    other areas neither crash the search nor skew it."""
    mover = state.entity(mover_id)
    at = mover.at()
    if at is None:
        return None
    foe_positions = [
        foe_at
        for foe in foes
        if foe in state.entities and (foe_at := state.entity(foe).at()) is not None
    ]
    foe_distances = [_distances(state, foe_at, mover_id) for foe_at in foe_positions]
    best: tuple[int, str, PosId] | None = None
    for token, destination in sorted(state.exits_from(at).items()):
        if not _passable(state, destination, mover_id):
            continue
        nearest = min(
            (distances.get(destination, 10**9) for distances in foe_distances),
            default=10**9,
        )
        if best is None or nearest > best[0]:
            best = (nearest, token, destination)
    if best is None:
        return None
    return Moved(actor=mover_id, origin=at, destination=best[2], exit=best[1])


def _battle_joiners(state: WorldState, engager: Entity) -> tuple[EntityId, ...]:
    """Who is drawn into a battle: the engager plus every hostile in the area
    already fighting (aggroed) or in melee range. Nobody freezes mid-fight
    just because a formal battle started next to them."""
    player_at = state.entity(PLAYER).at()
    assert player_at is not None
    space = state.areas[player_at.area]
    joiners = {engager.id}
    for hostile in hostile_actors(state):
        at = hostile.at()
        if at is None or at.area != player_at.area:
            continue
        if state.flags.get(aggro_flag(hostile.id)) or melee_adjacent(
            space, at, player_at
        ):
            joiners.add(hostile.id)
    return tuple(sorted(joiners))


def _arena_placement(
    state: WorldState, arena_name: str, order: tuple[EntityId, ...]
) -> tuple[tuple[Event, ...], tuple[tuple[EntityId, PosId], ...]] | None:
    """Moves into the arena plus the way home, or ``None`` when the arena
    cannot seat everyone (the battle falls back to the menu presentation)."""
    space = state.areas[arena_name]
    floors = [
        pos
        for pos in space.positions()
        if space.blocked_reason(state, pos, PLAYER) is None
    ]
    combatants = [PLAYER, *[c for c in order if c != PLAYER]]
    if len(floors) < len(combatants):
        return None
    moves: list[Event] = []
    returns: list[tuple[EntityId, PosId]] = []
    for combatant, destination in zip(combatants, floors, strict=False):
        origin = state.entity(combatant).at()
        assert origin is not None
        returns.append((combatant, origin))
        moves.append(
            Moved(
                actor=combatant,
                origin=origin,
                destination=destination,
                exit="arena",
            )
        )
    return tuple(moves), tuple(returns)


def _engage(
    state: WorldState, entity: Entity, rng: Rng
) -> tuple[tuple[Event, ...], Rng]:
    """A formal opponent opens a battle instead of trading skirmish blows.

    A menu battle grants pre-emptive strikes to foes that outrolled the
    player. An arena battle (the engager names one) instead moves everyone
    onto the battlefield: placement is the engagement round and replaces the
    pre-emptive strikes — the foes act from their placed tiles next round,
    which on a small arena may already be within reach (design 0006 §2).
    """
    foes = _battle_joiners(state, entity)
    order, rng = roll_initiative(state, (PLAYER, *foes), rng)
    events: list[Event] = []
    for foe in foes:
        events.extend(provoke(state, foe))

    assert entity.ai is not None
    placement = None
    if entity.ai.arena is not None:
        placement = _arena_placement(state, entity.ai.arena, order)
    if placement is not None:
        moves, returns = placement
        events.append(ModePushed(mode=MODE_BATTLE, initiative=order, returns=returns))
        events.extend(moves)
        return tuple(events), rng

    events.append(ModePushed(mode=MODE_BATTLE, initiative=order))
    state = fold(state, tuple(events))
    for combatant in order:
        if combatant == PLAYER:
            break
        if combatant not in state.entities or state.flags.get(PLAYER_DEFEATED):
            continue
        struck, rng = strike(state, combatant, PLAYER, rng)
        events.extend(struck)
        state = fold(state, struck)
    return tuple(events), rng


def _pursue(
    state: WorldState, entity: Entity, rng: Rng
) -> tuple[tuple[Event, ...], Rng]:
    """The one pursuit rule, shared by exploration hostiles and arena foes:
    strike when in melee reach of the player, else cast when able, else
    close one step (design 0007 §3: a hostile casts when it cannot strike).
    Casting is gated to the player's own area — a caster has ears but not
    artillery, so a player in another area is chased, never bombarded.
    """
    player_at = state.entity(PLAYER).at()
    at = entity.at()
    if player_at is None or at is None:
        return (), rng
    if at.area == player_at.area:
        if melee_adjacent(state.areas[at.area], at, player_at):
            return strike(state, entity.id, PLAYER, rng)
        ranged = next(
            (a for a in castable(state, entity.id) if a.targeting == TARGET_FOE), None
        )
        if ranged is not None:
            return cast_events(
                state, entity.id, ranged.id, PLAYER, (PLAYER,), rng, spend_turn=False
            )
    moved = _chase_step(state, entity, player_at)
    return ((moved,) if moved is not None else ()), rng


def _act(state: WorldState, entity: Entity, rng: Rng) -> tuple[tuple[Event, ...], Rng]:
    """One AI actor's turn: wake if provoked, then fight or give chase.

    Melee only exists inside one area; an aggroed hostile in another area
    chases through the same movement graph the player uses, portals included.
    """
    player_at = state.entity(PLAYER).at()
    at = entity.at()
    if player_at is None or at is None:
        return (), rng
    adjacent = at.area == player_at.area and melee_adjacent(
        state.areas[at.area], at, player_at
    )

    aggroed = bool(state.flags.get(aggro_flag(entity.id)))
    if not aggroed and not adjacent:
        return (), rng

    events: list[Event] = []
    if not aggroed:
        events.extend(provoke(state, entity.id))
        state = fold(state, tuple(events))

    assert entity.ai is not None
    if adjacent and entity.ai.engages:
        engaged, rng = _engage(state, entity, rng)
        events.extend(engaged)
        return tuple(events), rng
    pursued, rng = _pursue(state, entity, rng)
    events.extend(pursued)
    return tuple(events), rng


def _queue(state: WorldState) -> tuple[EntityId, ...]:
    """The scheduler's configuration per mode (ADR-004): battle serves the
    initiative queue; every other mode serves the activity list — talking or
    picking a lock does not stop the world, and a hostile that reaches the
    player mid-conversation interrupts it with a battle."""
    if state.mode == MODE_BATTLE:
        return tuple(c for c in state.initiative if c != PLAYER)
    return tuple(actor.id for actor in hostile_actors(state))


def _take_turn(
    state: WorldState, actor_id: EntityId, rng: Rng
) -> tuple[tuple[Event, ...], Rng]:
    """One AI turn under the active mode's rules."""
    if state.mode == MODE_BATTLE:
        if not state.battle_returns:
            # Menu battle abstracts distance: a combatant simply strikes.
            return strike(state, actor_id, PLAYER, rng)
        # Arena battle: the spatial model, unchanged (0003 §10.1).
        return _pursue(state, state.entity(actor_id), rng)
    return _act(state, state.entity(actor_id), rng)


def battle_homecoming(state: WorldState) -> tuple[Event, ...]:
    """Moves returning every surviving combatant to its recorded origin.

    Emitted before any battle pop; the dead are simply skipped, and the
    ModePopped fold clears the table."""
    moves: list[Event] = []
    for combatant, origin in state.battle_returns:
        if combatant not in state.entities:
            continue
        current = state.entity(combatant).at()
        if current is None or current == origin:
            continue
        moves.append(
            Moved(actor=combatant, origin=current, destination=origin, exit="return")
        )
    return tuple(moves)


def _expired_statuses(state: WorldState) -> tuple[Event, ...]:
    """Every status whose clock ran out, in sorted order, as events — expiry
    replays like everything else (design 0004 §3)."""
    expired: list[Event] = []
    for entity_id in sorted(state.entities):
        statuses = state.entities[entity_id].statuses
        if statuses is None:
            continue
        for status, expires in sorted(statuses.active):
            if expires <= state.turn:
                expired.append(StatusExpired(target=entity_id, status=status))
    return tuple(expired)


def _battle_outcome(state: WorldState) -> tuple[Event, ...]:
    """Victory or defeat pops the battle with its outcome (0003 §10.1)."""
    if state.mode != MODE_BATTLE:
        return ()
    foes_alive = any(
        combatant != PLAYER and combatant in state.entities
        for combatant in state.initiative
    )
    if not foes_alive:
        return (
            *battle_homecoming(state),
            ModePopped(mode=MODE_BATTLE, outcome="victory"),
        )
    if state.flags.get(PLAYER_DEFEATED):
        return (
            *battle_homecoming(state),
            ModePopped(mode=MODE_BATTLE, outcome="defeat"),
        )
    return ()


def run(
    state: WorldState,
    rng: Rng,
    *,
    prior: tuple[Event, ...],
    opening: WorldState,
) -> tuple[tuple[Event, ...], WorldState, Rng]:
    """Grant every due AI actor its turn, folding as it goes.

    One loop serves both scheduler configurations; the queue and the per-actor
    rules come from the active mode. Later actors see the effects of earlier
    ones, and the round stops the moment the player is defeated or the mode
    changes (an engagement hands the rest of the round to the battle). The
    epilogue then fires status/perk hooks over the whole round's events —
    ``prior`` is the player's half, already folded into ``state`` by the
    caller, and ``opening`` is the step's starting state so each trigger is
    judged at its own moment — sweeps expired statuses, and pops a finished
    battle with its outcome. Returns the folded state alongside the events so
    the caller does not fold them a second time.
    """
    opening_mode = state.mode
    events: list[Event] = []
    for actor_id in _queue(state):
        if state.flags.get(PLAYER_DEFEATED) or state.mode != opening_mode:
            break
        if actor_id not in state.entities:
            continue
        acted, rng = _take_turn(state, actor_id, rng)
        events.extend(acted)
        state = fold(state, acted)

    hooked, state, rng = hook_events(opening, state, (*prior, *events), rng)
    events.extend(hooked)

    expiries = _expired_statuses(state)
    events.extend(expiries)
    state = fold(state, expiries)

    outcome = _battle_outcome(state)
    events.extend(outcome)
    state = fold(state, outcome)

    # A defeated player cannot keep choosing or picking: collapse any focus
    # mode so the defeated grammar (look only) applies.
    while state.flags.get(PLAYER_DEFEATED) and state.mode in FOCUS_MODES:
        popped = ModePopped(mode=state.mode, outcome="defeat")
        events.append(popped)
        state = fold(state, (popped,))
    return tuple(events), state, rng
