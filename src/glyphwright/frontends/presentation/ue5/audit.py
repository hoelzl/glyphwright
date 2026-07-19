"""The drift-detection audit: does the level geometry still match the grid?

Design 0012 §11.5 keeps collision drift *out* of the per-run oracle fingerprint
(the fingerprint is deliberately coarse) and detects it here instead, on
demand: re-run the passable-edge set through UE5's ``trace_world`` and report
every edge the grid calls passable that the geometry blocks.

This detects one direction of drift — "geometry blocks what should be open" —
and deliberately not the other: a wall that *disappears* in UE5 leaves no
passable edge to trace, so a missing wall is invisible here (a floor→wall audit
would be a separate pass over wall cells). It is also a single horizontal ray
per edge at ``probe_height``, so it assumes the collision that matters to
movement crosses that height; an obstacle entirely below it is not seen. Both
are conscious consequences of §11.5's on-demand, coarse contract.

The split mirrors the importer's: deriving the passable-edge set and
classifying the traced results are *pure* (no editor, no MCP), so they are
verifiable offline; only :func:`audit` touches the network, through the
injected :class:`UE5Client`.

World projection matches the importer exactly — a grid cell ``(x, y)`` centers
at ``((x + 0.5) * tile, (y + 0.5) * tile, z)`` — so the audit traces the same
coordinates the importer spawns at.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from glyphwright.frontends.presentation.manifest import PresentationManifest
from glyphwright.frontends.presentation.ue5.client import UE5Client
from glyphwright.frontends.presentation.ue5.importer import DEFAULT_TILE_CM
from glyphwright.world.grid import FLOOR, GridSpace
from glyphwright.world.space import PosId

#: Height above the floor (centimeters) at which edges are traced. A coarse,
#: unverified default: it assumes the collision that matters to movement
#: crosses this height and that the floor's own surface sits below it (a floor
#: top above it would register as a near-zero self-hit). Callers with a
#: different floor/obstacle profile should pass an explicit ``probe_height``.
DEFAULT_PROBE_HEIGHT_CM = 50.0


@dataclass(frozen=True, slots=True)
class Edge:
    """One adjacent pair of floor cells, canonicalized so each unordered pair
    appears once (``a`` precedes ``b`` in numeric reading order). Passability
    here is terrain, not occupancy: the audit checks the *map's* geometry, not
    where actors stand."""

    a: PosId
    b: PosId


@dataclass(frozen=True, slots=True)
class Drift:
    """An edge the grid calls passable that UE5's collision blocks.

    ``expected`` is the full center-to-center distance (centimeters); ``hit``
    is the distance ``trace_world`` actually reported before geometry stopped
    the ray (``None`` would mean unobstructed, which is not drift).
    """

    edge: Edge
    expected: float
    hit: float


def _cell_xy(pos: PosId) -> tuple[int, int]:
    x_text, _, y_text = pos.local.partition(",")
    return int(x_text), int(y_text)


def _cell_center(pos: PosId, tile: float, height: float) -> tuple[float, float, float]:
    """The world-space center of a grid cell, matching the importer's projection."""
    x, y = _cell_xy(pos)
    return ((x + 0.5) * tile, (y + 0.5) * tile, height)


def passable_edges(grid: GridSpace) -> tuple[Edge, ...]:
    """Every adjacent pair of floor cells in the grid, in deterministic order.

    Only terrain decides passability: a wall cell terminates no edge, and actor
    occupancy is ignored (this audits the map's geometry, not a live run). Each
    unordered pair appears once. Order follows grid reading order (y, then x)
    so reports are stable and spatially readable.
    """
    edges: list[Edge] = []
    for y in range(grid.height):
        for x in range(grid.width):
            here = grid.pos(x, y)
            if grid.terrain(here) != FLOOR:
                continue
            for neighbour in grid.exits(here).values():
                if grid.terrain(neighbour) != FLOOR:
                    continue
                # Canonicalize: emit each unordered pair once, from the cell
                # that comes first in numeric reading order, so east/south
                # edges are not duplicated as their west/north mirrors.
                neighbour_x, neighbour_y = _cell_xy(neighbour)
                if (y, x) < (neighbour_y, neighbour_x):
                    edges.append(Edge(a=here, b=neighbour))
    return tuple(edges)


def _edge_length(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    """Center-to-center distance; for axis-adjacent cells this is exactly ``tile``."""
    return math.dist(a, b)


async def audit(
    client: UE5Client,
    grid: GridSpace,
    manifest: PresentationManifest,
    *,
    probe_height: float = DEFAULT_PROBE_HEIGHT_CM,
    tolerance: float = 1.0,
) -> tuple[Drift, ...]:
    """Trace every passable edge and return the ones UE5's collision blocks.

    This is the only audit function that touches the network. For each edge the
    grid calls passable, it traces cell-center to cell-center at
    ``probe_height``; an unobstructed ray returns ``None`` (no drift), and a
    hit within ``tolerance`` of the full length is treated as reaching the far
    cell (no drift). Anything shorter means geometry stands where the semantics
    expect open floor — a :class:`Drift`, returned in edge order. Disagreement
    is signal, not failure: the audit *reports* drift, it does not raise.
    """
    tile = float(manifest.hints.get("tile_size_cm", DEFAULT_TILE_CM))  # type: ignore[arg-type]
    drifts: list[Drift] = []
    for edge in passable_edges(grid):
        start = _cell_center(edge.a, tile, probe_height)
        end = _cell_center(edge.b, tile, probe_height)
        expected = _edge_length(start, end)
        hit = await client.trace_world(start, end)
        if hit is None:
            continue  # unobstructed: geometry agrees the edge is open
        if expected - hit <= tolerance:
            continue  # hit at (within tolerance of) the far cell: not blocked
        drifts.append(Drift(edge=edge, expected=expected, hit=hit))
    return tuple(drifts)
