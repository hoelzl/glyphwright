"""The UE5 importer: a SceneGraph becomes a deterministic spawn plan (14C).

The plan is *pure* — no editor, no MCP, no wall clock — so it is verified by
goldens offline; only executing a plan against an editor touches the network
(the opt-in e2e). This is the build-time half of "the manifest maps packs to
UE5 assets" (0012 §9): the pack's SceneGraph carries *what* is where, the
manifest carries *which mesh* stands for it, and the importer projects the
grid into UE5 centimeter space via the manifest's hints.
"""

from __future__ import annotations

from glyphwright.frontends.presentation.manifest import PresentationManifest
from glyphwright.frontends.presentation.scenegraph import (
    ACTOR,
    Camera,
    Placement,
    SceneGraph,
)


def _graph(placements: list[Placement], manifest: PresentationManifest) -> SceneGraph:
    return SceneGraph(
        placements=tuple(placements),
        camera=Camera(origin=(0, 0), focus=None),
        transitions=(),
        affordances=(),
        manifest_hash=manifest.hash,
    )


def _manifest(
    bindings: dict[str, str], hints: dict[str, object]
) -> PresentationManifest:
    return PresentationManifest(bindings=bindings, decoration={}, hints=hints)


def test_every_placement_spawns_in_stable_order() -> None:
    from glyphwright.frontends.presentation.ue5.importer import plan_spawns

    manifest = _manifest({"#": "/Game/Mesh/Wall", ".": "/Game/Mesh/Floor"}, {})
    graph = _graph(
        [
            Placement("#", "village:0,0", (0, 0, 0), "/Game/Mesh/Wall", "ground"),
            Placement(".", "village:1,0", (1, 0, 0), "/Game/Mesh/Floor", "ground"),
        ],
        manifest,
    )
    plan = plan_spawns(graph, manifest)
    assert [op.semantic_pos for op in plan] == ["village:0,0", "village:1,0"]


def test_grid_cells_project_to_centimeters_via_the_tile_hint() -> None:
    from glyphwright.frontends.presentation.ue5.importer import plan_spawns

    manifest = _manifest({"#": "/Game/Mesh/Wall"}, {"tile_size_cm": 100.0})
    graph = _graph(
        [Placement("#", "village:7,3", (7, 3, 0), "/Game/Mesh/Wall", "ground")],
        manifest,
    )
    (op,) = plan_spawns(graph, manifest)
    # Cell-center projection: (x + 0.5) * tile_size.
    assert op.location == (750.0, 350.0, 0.0)


def test_tiers_project_to_distinct_heights() -> None:
    from glyphwright.frontends.presentation.ue5.importer import plan_spawns

    manifest = _manifest(
        {".": "/Game/Mesh/Floor", "@": "/Game/Mesh/Hero"},
        {"tile_size_cm": 100.0, "tier_height": {"ground": 0.0, "actor": 90.0}},
    )
    graph = _graph(
        [
            Placement(".", "village:0,0", (0, 0, 0), "/Game/Mesh/Floor", "ground"),
            Placement("@", "village:0,0", (0, 0, 0), "/Game/Mesh/Hero", ACTOR),
        ],
        manifest,
    )
    floor, hero = plan_spawns(graph, manifest)
    assert floor.location[2] == 0.0
    assert hero.location[2] == 90.0


def test_spawn_names_are_stable_and_collision_free() -> None:
    from glyphwright.frontends.presentation.ue5.importer import plan_spawns

    manifest = _manifest({"#": "/Game/Mesh/Wall"}, {"tile_size_cm": 100.0})
    graph = _graph(
        [Placement("#", "village:7,3", (7, 3, 0), "/Game/Mesh/Wall", "ground")],
        manifest,
    )
    (op,) = plan_spawns(graph, manifest)
    assert op.name == "gw_village_7_3"


def test_the_plan_is_deterministic_across_compose() -> None:
    from glyphwright.frontends.presentation.ue5.importer import plan_spawns

    manifest = _manifest({"#": "/Game/Mesh/Wall"}, {"tile_size_cm": 100.0})
    placements = [
        Placement("#", "village:0,1", (0, 1, 0), "/Game/Mesh/Wall", "ground"),
        Placement("#", "village:0,0", (0, 0, 0), "/Game/Mesh/Wall", "ground"),
    ]
    a = plan_spawns(_graph(placements, manifest), manifest)
    b = plan_spawns(_graph(list(reversed(placements)), manifest), manifest)
    assert [op.name for op in a] == [op.name for op in b]
