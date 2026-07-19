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
from glyphwright.frontends.presentation.ue5.client import UE5Client, UE5Error

#: Default grid-cell footprint in UE5 units (centimeters) when the manifest
#: does not declare ``tile_size_cm``.
DEFAULT_TILE_CM = 100.0

#: Default per-tier heights. Ground sits at z=0; fixtures and actors stand on
#: the floor unless the manifest's ``tier_height`` hint says otherwise.
DEFAULT_TIER_HEIGHT = {"ground": 0.0, "fixture": 0.0, "actor": 0.0}

#: Reading order of tiers within a cell, for the canonical plan sort.
_TIER_ORDER = {"ground": 0, "fixture": 1, "actor": 2}


@dataclass(frozen=True, slots=True)
class SpawnOp:
    """One actor to place: a stable name, a mesh, and a UE5 world location."""

    name: str
    semantic_pos: str
    asset_path: str
    location: tuple[float, float, float]
    tier: str


class ImporterError(ValueError):
    """A SceneGraph that cannot be planned, located by what was wrong."""


def _tile_size(manifest: PresentationManifest) -> float:
    value = manifest.hints.get("tile_size_cm", DEFAULT_TILE_CM)
    return float(value)  # type: ignore[arg-type]


def _tier_height(manifest: PresentationManifest, tier: str) -> float:
    heights = manifest.hints.get("tier_height", DEFAULT_TIER_HEIGHT)
    assert isinstance(heights, dict)
    return float(heights.get(tier, 0.0))


def _parse_pos(semantic_pos: str) -> tuple[str, int, int]:
    """``village:7,3`` -> ``("village", 7, 3)``, or a located ``ImporterError``.

    The absolute grid coordinate is the authoritative position: ``compose``
    bakes the viewport origin into ``semantic_pos`` while ``render_pos`` stays
    viewport-local, so a panned scene must be planned from here, not from
    ``render_pos`` (which would double-offset).
    """
    area, sep, local = semantic_pos.partition(":")
    xs, comma, ys = local.partition(",")
    if not sep or not comma:
        raise ImporterError(
            f"semantic_pos {semantic_pos!r} is not 'area:x,y'; cannot place it"
        )
    try:
        return area, int(xs), int(ys)
    except ValueError as error:
        raise ImporterError(
            f"semantic_pos {semantic_pos!r} has non-integer coordinates"
        ) from error


def _spawn_name(area: str, x: int, y: int, tier: str) -> str:
    """A stable, collision-free actor name for a placement.

    ``gw_village_ground_7_3``. The ``gw_`` prefix keeps importer actors
    findable and removable as a group; the tier segment disambiguates the
    ground/fixture/actor stack that shares one grid cell; the position suffix
    means re-importing the same SceneGraph reuses the same names rather than
    accumulating duplicates.
    """
    return f"gw_{area}_{tier}_{x}_{y}"


def plan_spawns(graph: SceneGraph, manifest: PresentationManifest) -> list[SpawnOp]:
    """Map a SceneGraph's placements to an ordered, deterministic spawn plan.

    Pure: same graph, same manifest, same plan. World coordinates come from
    ``semantic_pos`` (the absolute grid cell), never from the viewport-local
    ``render_pos``. Order is canonical — grid reading order (y, then x, then
    tier) — so equal SceneGraphs plan identically and the plan reads spatially
    for review, not lexicographically (``village:10,0`` after ``village:2,0``).
    """
    tile = _tile_size(manifest)
    plan: list[SpawnOp] = []
    for placement in graph.placements:
        area, x, y = _parse_pos(placement.semantic_pos)
        location = (
            (x + 0.5) * tile,
            (y + 0.5) * tile,
            _tier_height(manifest, placement.tier),
        )
        plan.append(
            SpawnOp(
                name=_spawn_name(area, x, y, placement.tier),
                semantic_pos=placement.semantic_pos,
                asset_path=placement.asset_id,
                location=location,
                tier=placement.tier,
            )
        )
    plan.sort(
        key=lambda op: (
            _parse_pos(op.semantic_pos)[2],  # y
            _parse_pos(op.semantic_pos)[1],  # x
            _TIER_ORDER.get(op.tier, len(_TIER_ORDER)),
            op.name,
        )
    )
    return plan


async def apply(client: UE5Client, plan: list[SpawnOp]) -> list[str]:
    """Execute a spawn plan against a live editor; returns actor paths.

    This is the only importer function that touches the network. Each op
    spawns its mesh at its projected location; the editor resolves the asset
    path. A spawn that fails aborts the import with a :class:`UE5Error` naming
    the op's actor name and semantic position, so a partial import is
    attributable rather than silent.
    """
    spawned: list[str] = []
    for op in plan:
        try:
            result = await client.spawn_from_class(
                op.asset_path, name=op.name, location=op.location
            )
        except UE5Error:
            raise
        except Exception as error:
            raise UE5Error(
                f"import failed at {op.name} ({op.semantic_pos}): {error}"
            ) from error
        spawned.append(str(result))
    return spawned
