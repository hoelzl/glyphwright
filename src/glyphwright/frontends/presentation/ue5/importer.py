"""The UE5 importer: a SceneGraph becomes a spawn plan (design 0012 §9, 14C).

The plan is the build-time half of "the manifest maps packs to UE5 assets."
It is *pure* — no editor, no MCP, no wall clock — so the whole mapping is
verifiable offline by goldens; only :func:`apply` touches the network, and it
does so through the injected :class:`UE5Client`, which the opt-in e2e binds to
a live editor. The pack's SceneGraph carries *what* is where, the manifest
carries *which mesh* stands for it, and the importer projects the grid into
UE5 centimeter space via the manifest's hints.
"""

from __future__ import annotations

from dataclasses import dataclass

from glyphwright.frontends.presentation.manifest import PresentationManifest
from glyphwright.frontends.presentation.scenegraph import SceneGraph
from glyphwright.frontends.presentation.ue5.client import UE5Client

#: Default grid-cell footprint in UE5 units (centimeters) when the manifest
#: does not declare ``tile_size_cm``.
DEFAULT_TILE_CM = 100.0

#: Default per-tier heights. Ground sits at z=0; actors stand on the floor.
DEFAULT_TIER_HEIGHT = {"ground": 0.0, "fixture": 0.0, "actor": 0.0}


@dataclass(frozen=True, slots=True)
class SpawnOp:
    """One actor to place: a stable name, a mesh, and a UE5 world location."""

    name: str
    semantic_pos: str
    asset_path: str
    location: tuple[float, float, float]


def _tile_size(manifest: PresentationManifest) -> float:
    value = manifest.hints.get("tile_size_cm", DEFAULT_TILE_CM)
    return float(value)  # type: ignore[arg-type]


def _tier_height(manifest: PresentationManifest, tier: str) -> float:
    heights = manifest.hints.get("tier_height", DEFAULT_TIER_HEIGHT)
    assert isinstance(heights, dict)
    return float(heights.get(tier, 0.0))  # type: ignore[arg-type]


def _spawn_name(semantic_pos: str) -> str:
    """A stable, collision-free actor name from a semantic position.

    ``village:7,3`` -> ``gw_village_7_3``. The ``gw_`` prefix keeps importer
    actors findable and removable as a group, and the position-derived suffix
    means re-importing the same SceneGraph reuses the same names rather than
    accumulating duplicates.
    """
    area, _, local = semantic_pos.partition(":")
    x, _, y = local.partition(",")
    return f"gw_{area}_{x}_{y}"


def plan_spawns(graph: SceneGraph, manifest: PresentationManifest) -> list[SpawnOp]:
    """Map a SceneGraph's placements to an ordered, deterministic spawn plan.

    Pure: same graph, same manifest, same plan. Order is canonical — sorted by
    semantic position — so equal SceneGraphs plan identically regardless of
    the placement iteration order, and the plan's hash-like identity is stable
    for goldens and review.
    """
    tile = _tile_size(manifest)
    plan: list[SpawnOp] = []
    for placement in graph.placements:
        x, y, _ = placement.render_pos
        location = (
            (x + 0.5) * tile,
            (y + 0.5) * tile,
            _tier_height(manifest, placement.tier),
        )
        plan.append(
            SpawnOp(
                name=_spawn_name(placement.semantic_pos),
                semantic_pos=placement.semantic_pos,
                asset_path=placement.asset_id,
                location=location,
            )
        )
    plan.sort(key=lambda op: op.semantic_pos)
    return plan


async def apply(client: UE5Client, plan: list[SpawnOp]) -> list[str]:
    """Execute a spawn plan against a live editor; returns actor paths.

    This is the only importer function that touches the network. Each op
    spawns its mesh at its projected location; the editor resolves the asset
    path. Errors propagate as :class:`UE5Error` with the failing op named, so
    a partial import is attributable rather than silent.
    """
    spawned: list[str] = []
    for op in plan:
        result = await client.spawn_from_class(
            op.asset_path, name=op.name, location=op.location
        )
        spawned.append(str(result))
    return spawned
