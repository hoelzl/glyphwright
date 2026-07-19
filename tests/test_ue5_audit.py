"""The drift-detection audit: passable-edge derivation and classification.

These tests inject a fake transport, so the audit is verified offline; the
live editor is exercised only by the opt-in e2e mark. The pure half
(``passable_edges``) is asserted directly; the network half (``audit``) runs
through a ``UE5Client`` whose fake transport answers ``trace_world`` from a
scripted hit table, mirroring the confirmed ``{"returnValue": ...}`` envelope.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable
from typing import Any

import pytest

pytest.importorskip("anyio")
import anyio  # noqa: E402

from glyphwright.frontends.presentation.manifest import PresentationManifest
from glyphwright.frontends.presentation.ue5.audit import (
    DEFAULT_PROBE_HEIGHT_CM,
    Drift,
    Edge,
    audit,
    passable_edges,
)
from glyphwright.frontends.presentation.ue5.client import UE5Client
from glyphwright.world.grid import GridSpace
from glyphwright.world.space import PosId

#: A trace key: (start, end) world coordinates.
TraceKey = tuple[tuple[float, float, float], tuple[float, float, float]]


def run[T](coro: Awaitable[T]) -> T:
    async def go() -> T:
        return await coro

    return anyio.run(go)


def _manifest(tile: float = 100.0) -> PresentationManifest:
    return PresentationManifest(
        bindings={}, decoration={}, hints={"tile_size_cm": tile}
    )


# A 3x2 room, all floor.
OPEN = GridSpace.from_text("room", "...\n...")
# A 3x1 corridor with the middle cell walled off.
WALLED = GridSpace.from_text("corridor", ".#.")


def _pos(area: str, x: int, y: int) -> PosId:
    return PosId(area=area, local=f"{x},{y}")


def test_passable_edges_enumerates_each_floor_pair_once() -> None:
    edges = passable_edges(OPEN)
    # Horizontal edges (rows y=0 and y=1): (0,y)-(1,y), (1,y)-(2,y) -> 4.
    # Vertical edges (columns x=0,1,2): (x,0)-(x,1) -> 3. Total 7.
    assert len(edges) == 7
    # Each unordered pair appears once, canonicalized a-before-b.
    assert all((e.a.area, e.a.local) < (e.b.area, e.b.local) for e in edges)
    assert len({(e.a, e.b) for e in edges}) == 7  # no duplicates
    assert Edge(a=_pos("room", 0, 0), b=_pos("room", 1, 0)) in edges
    assert Edge(a=_pos("room", 0, 0), b=_pos("room", 0, 1)) in edges


def test_passable_edges_ignores_walls_and_terminates_at_them() -> None:
    edges = passable_edges(WALLED)
    # Only the left cell (0,0) and right cell (2,0) are floor; the wall between
    # them means there is no passable edge at all.
    assert edges == ()


def _tracing_client(
    hits: dict[TraceKey, float | None],
) -> tuple[UE5Client, list[dict[str, Any]]]:
    """A client whose trace_world answers from ``hits``, keyed by (start, end),
    recording each call's arguments for assertion."""
    seen: list[dict[str, Any]] = []

    async def transport(tool: str, arguments: dict[str, object]) -> object:
        assert tool == "call_tool"
        assert arguments["tool_name"] == "trace_world"
        args = arguments["arguments"]
        assert isinstance(args, dict)
        seen.append(args)
        s, e = args["start"], args["end"]
        assert isinstance(s, dict) and isinstance(e, dict)
        key: TraceKey = (
            (s["x"], s["y"], s["z"]),
            (e["x"], e["y"], e["z"]),
        )
        return {"returnValue": json.dumps(hits.get(key))}

    return UE5Client(transport), seen


def test_audit_reports_no_drift_when_every_edge_is_clear() -> None:
    client, _ = _tracing_client({})  # default None: unobstructed
    assert run(audit(client, OPEN, _manifest())) == ()


def test_audit_traces_cell_centers_at_the_probe_height() -> None:
    client, seen = _tracing_client({})
    run(audit(client, WALLED, _manifest(tile=100.0)))
    # WALLED has no passable edges, so nothing is traced.
    assert seen == []

    client, seen = _tracing_client({})
    run(audit(client, OPEN, _manifest(tile=100.0)))
    # The edge (0,0)-(1,0) traces center-to-center: (50,50,h) -> (150,50,h).
    first = seen[0]
    assert first["start"] == {"x": 50.0, "y": 50.0, "z": DEFAULT_PROBE_HEIGHT_CM}
    assert first["end"] == {"x": 150.0, "y": 50.0, "z": DEFAULT_PROBE_HEIGHT_CM}


def test_audit_flags_an_edge_blocked_short_of_the_far_cell() -> None:
    # The (0,0)-(1,0) edge of OPEN: tile=100, expected distance 100.
    start = (50.0, 50.0, DEFAULT_PROBE_HEIGHT_CM)
    end = (150.0, 50.0, DEFAULT_PROBE_HEIGHT_CM)
    client, _ = _tracing_client({(start, end): 40.0})  # wall 40cm in
    drifts: tuple[Drift, ...] = run(audit(client, OPEN, _manifest(tile=100.0)))
    assert len(drifts) == 1
    drift = drifts[0]
    assert drift.edge == Edge(a=_pos("room", 0, 0), b=_pos("room", 1, 0))
    assert drift.expected == 100.0
    assert drift.hit == 40.0


def test_audit_tolerates_a_hit_at_the_far_cell_boundary() -> None:
    # A hit within tolerance of the full length is the far cell's own floor
    # geometry, not a blocker on the edge.
    start = (50.0, 50.0, DEFAULT_PROBE_HEIGHT_CM)
    end = (150.0, 50.0, DEFAULT_PROBE_HEIGHT_CM)
    client, _ = _tracing_client({(start, end): 99.5})  # within tolerance 1.0
    assert run(audit(client, OPEN, _manifest(tile=100.0))) == ()


def test_audit_reports_drift_in_edge_order() -> None:
    # Block two edges; the report must follow passable_edges order (y, then x).
    def key(x0: float, y0: float, x1: float, y1: float) -> TraceKey:
        h = DEFAULT_PROBE_HEIGHT_CM
        return (
            (x0 + 0.5) * 100.0,
            (y0 + 0.5) * 100.0,
            h,
        ), (
            (x1 + 0.5) * 100.0,
            (y1 + 0.5) * 100.0,
            h,
        )

    hits: dict[TraceKey, float | None] = {
        key(1, 0, 2, 0): 30.0,
        key(0, 0, 1, 0): 20.0,
    }
    client, _ = _tracing_client(hits)
    drifts: tuple[Drift, ...] = run(audit(client, OPEN, _manifest()))
    assert [d.edge for d in drifts] == [
        Edge(a=_pos("room", 0, 0), b=_pos("room", 1, 0)),
        Edge(a=_pos("room", 1, 0), b=_pos("room", 2, 0)),
    ]
