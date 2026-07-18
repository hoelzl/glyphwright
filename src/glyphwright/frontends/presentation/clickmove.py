"""Click-to-move: a presentation macro that compiles to the grammar (0012 §6).

The player clicks a reachable cell; ``expand_click`` resolves that against the
*live* engine — where the player stands, what the grid's topology allows — and
returns the deterministic sequence of ``Move`` commands the pure pathfinder
computes. Each command is then stepped through the kernel exactly as if typed,
so occupancy refusals, battle engagement, and every other world rule apply
identically to the click and to the equivalent keystrokes. The macro adds no
kernel semantics; it is convenience that compiles down.
"""

from __future__ import annotations

from glyphwright.api import Engine
from glyphwright.kernel.commands import Move
from glyphwright.world.grid import GridSpace
from glyphwright.world.space import PosId


def expand_click(
    engine: Engine, area: str, target: tuple[int, int]
) -> tuple[Move, ...] | None:
    """The ``Move`` sequence to walk the player to ``target``, or ``None``.

    ``None`` means the click names no reachable walk: the cell is a wall, off
    the map, in another area, or enclosed. The sequence is the pathfinder's
    deterministic answer over the grid's topology; dynamic blockers are left
    for the kernel to refuse at execution time, which is the same outcome an
    agent gets typing the moves.
    """
    frame = engine.frame()
    player = next((actor for actor in frame.actors if actor.id == "player"), None)
    if player is None or player.at.area != area:
        return None
    space = engine_space(engine, area)
    if space is None:
        return None
    start = _coords(player.at)
    tokens = _find(space, start, target, seed=engine.fingerprint().seed)
    if tokens is None:
        return None
    return tuple(Move(token) for token in tokens)


def engine_space(engine: Engine, area: str) -> GridSpace | None:
    """The grid space for ``area`` in the engine's live world, if it is a grid.

    Reachable through the world state the engine already holds; only grid
    areas are walkable by the pathfinder (room-graph areas navigate by exit
    token, not by coordinate).
    """
    state = engine.snapshot()._state  # noqa: SLF001 - read-only access to topology
    space = state.areas.get(area)
    return space if isinstance(space, GridSpace) else None


def _coords(pos: PosId) -> tuple[int, int]:
    x_text, _, y_text = pos.local.partition(",")
    return int(x_text), int(y_text)


def _find(
    space: GridSpace, start: tuple[int, int], target: tuple[int, int], *, seed: int
) -> tuple[str, ...] | None:
    from glyphwright.frontends.presentation.pathfinding import find_path

    return find_path(space, start, target, seed=seed)
