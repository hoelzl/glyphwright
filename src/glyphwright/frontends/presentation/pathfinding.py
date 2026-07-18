"""A pure A* pathfinder over a grid's passable topology (design 0012 §6).

Click-to-move is a macro-command, not new kernel behavior: a click on a
reachable position expands here into the deterministic sequence of
``move <exit-token>`` commands that the kernel then validates one by one. The
expansion is a pure function of the map's topology, so the resulting event
stream is identical to having typed the moves — which is what keeps a click
session replayable byte-for-byte.

Determinism comes from two choices: the frontier is a priority queue ordered
by ``(cost, tie, token)`` so equal-cost candidates resolve by a fixed token
order rather than by heap accident, and the neighbour sweep follows the
space's own ordered exit enumeration. The seed is not read here — A* over a
fixed grid with a fixed tie order is already fully determined; the ``seed``
parameter is accepted so the call site can thread the run seed through for
future decoration without changing this signature.
"""

from __future__ import annotations

import heapq

from glyphwright.world.grid import GridSpace
from glyphwright.world.space import ExitToken, PosId

# A fixed token order breaks ties the same way on every run and every
# platform, independent of dict/heap insertion order.
_TOKEN_ORDER: tuple[ExitToken, ...] = ("north", "east", "south", "west")


def find_path(
    space: GridSpace,
    start: tuple[int, int],
    goal: tuple[int, int],
    *,
    seed: int = 0,
) -> tuple[ExitToken, ...] | None:
    """The move-token sequence from ``start`` to ``goal``, or ``None``.

    ``None`` means unreachable (a wall encloses the goal, or it is a wall).
    Terrain passability is the map's own: floors pass, walls do not. Dynamic
    blockers (other actors) are not pathable state — the kernel refuses an
    occupied step at execution time, which is exactly the rejection an agent
    would get typing the same moves.
    """
    if start == goal:
        return ()
    if not space.contains(space.pos(*goal)) or space.terrain(space.pos(*goal)) == "#":
        return None

    def heuristic(x: int, y: int) -> int:
        return abs(x - goal[0]) + abs(y - goal[1])

    # Frontier entries: (f, tie, g, x, y). ``tie`` orders equal-f candidates
    # deterministically; the path is reconstructed from ``came_from``.
    frontier: list[tuple[int, int, int, int, int]] = []
    counter = 0
    heapq.heappush(frontier, (heuristic(*start), 0, 0, start[0], start[1]))
    came_from: dict[tuple[int, int], tuple[tuple[int, int], ExitToken]] = {}
    best_g: dict[tuple[int, int], int] = {start: 0}

    while frontier:
        _, _, g, x, y = heapq.heappop(frontier)
        if (x, y) == goal:
            return _reconstruct(came_from, start, goal)
        if g > best_g.get((x, y), g):
            continue  # a stale entry; a cheaper route to (x, y) already won
        current = space.pos(x, y)
        exits = space.exits(current)
        for token in _TOKEN_ORDER:
            neighbour = exits.get(token)
            if neighbour is None:
                continue
            nx, ny = _coords(neighbour)
            if space.terrain(neighbour) == "#":
                continue
            step = g + 1
            if step < best_g.get((nx, ny), step + 1):
                best_g[(nx, ny)] = step
                came_from[(nx, ny)] = ((x, y), token)
                counter += 1
                heapq.heappush(
                    frontier, (step + heuristic(nx, ny), counter, step, nx, ny)
                )
    return None


def _reconstruct(
    came_from: dict[tuple[int, int], tuple[tuple[int, int], ExitToken]],
    start: tuple[int, int],
    goal: tuple[int, int],
) -> tuple[ExitToken, ...]:
    tokens: list[ExitToken] = []
    node = goal
    while node != start:
        previous, token = came_from[node]
        tokens.append(token)
        node = previous
    tokens.reverse()
    return tuple(tokens)


def _coords(pos: PosId) -> tuple[int, int]:
    """The ``(x, y)`` of a grid PosId, parsed from its local form."""
    x_text, _, y_text = pos.local.partition(",")
    return int(x_text), int(y_text)
