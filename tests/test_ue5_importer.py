"""The UE5 importer: a SceneGraph becomes a deterministic spawn plan (14C).

The plan is *pure* — no editor, no MCP, no wall clock — so it is verified by
goldens offline; only executing a plan against an editor touches the network
(the opt-in e2e). This is the build-time half of "the manifest maps packs to
UE5 assets" (0012 §9): the pack's SceneGraph carries *what* is where, the
manifest carries *which mesh* stands for it, and the importer projects the
grid into UE5 centimeter space via the manifest's hints.
"""

from __future__ import annotations

import pytest

pytest.importorskip("anyio")

import anyio  # noqa: E402

from glyphwright.frontends.presentation.manifest import (
    PresentationManifest,  # noqa: E402
)
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
    assert op.name == "gw_village_ground_7_3"


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


def test_world_coords_come_from_semantic_pos_not_viewport_local_render_pos() -> None:
    """A panned viewport leaves render_pos local but semantic_pos absolute
    (scenegraph.py bakes the origin into semantic_pos). The importer must use
    the absolute coords, or a panned scene re-imports its tiles double-offset.
    """
    from glyphwright.frontends.presentation.ue5.importer import plan_spawns

    manifest = _manifest({"#": "/Game/Mesh/Wall"}, {"tile_size_cm": 100.0})
    # Camera panned to (2, 1): render_pos is viewport-local (0, 0), but the
    # absolute cell is village:2,1.
    graph = _graph(
        [Placement("#", "village:2,1", (0, 0, 0), "/Game/Mesh/Wall", "ground")],
        manifest,
    )
    (op,) = plan_spawns(graph, manifest)
    assert op.location == (250.0, 150.0, 0.0)  # (2+.5)*100, (1+.5)*100


def test_tier_stacked_placements_get_distinct_names() -> None:
    """Ground+fixture+actor share a semantic_pos; names must not collide."""
    from glyphwright.frontends.presentation.ue5.importer import plan_spawns

    manifest = _manifest(
        {".": "/Game/Mesh/Floor", "O": "/Game/Mesh/Cask", "@": "/Game/Mesh/Hero"},
        {"tile_size_cm": 100.0},
    )
    graph = _graph(
        [
            Placement(".", "village:7,3", (0, 0, 0), "/Game/Mesh/Floor", "ground"),
            Placement("O", "village:7,3", (0, 0, 0), "/Game/Mesh/Cask", "fixture"),
            Placement("@", "village:7,3", (0, 0, 0), "/Game/Mesh/Hero", ACTOR),
        ],
        manifest,
    )
    names = [op.name for op in plan_spawns(graph, manifest)]
    assert len(names) == len(set(names)), f"colliding names: {names}"


def test_the_plan_sorts_in_grid_reading_order() -> None:
    """Canonical order is spatial (y then x), not lexicographic on the string
    (which would order village:10,0 before village:2,0)."""
    from glyphwright.frontends.presentation.ue5.importer import plan_spawns

    manifest = _manifest({"#": "/Game/Mesh/Wall"}, {"tile_size_cm": 100.0})
    graph = _graph(
        [
            Placement("#", "village:10,0", (10, 0, 0), "/Game/Mesh/Wall", "ground"),
            Placement("#", "village:2,0", (2, 0, 0), "/Game/Mesh/Wall", "ground"),
            Placement("#", "village:1,1", (1, 1, 0), "/Game/Mesh/Wall", "ground"),
        ],
        manifest,
    )
    order = [op.semantic_pos for op in plan_spawns(graph, manifest)]
    assert order == ["village:2,0", "village:10,0", "village:1,1"]


def test_apply_spawns_each_op_and_returns_actor_paths() -> None:
    from glyphwright.frontends.presentation.ue5.importer import SpawnOp, apply

    spawned: list[str] = []

    async def fake_spawn(
        class_path: str, *, name: str, location: tuple[float, float, float]
    ) -> str:
        spawned.append(name)
        return f"/Game/Maps/M.M:PersistentLevel.{name}"

    class _Fake:
        spawn_from_class = staticmethod(fake_spawn)

    plan = [
        SpawnOp(
            "gw_village_ground_0_0",
            "village:0,0",
            "/Game/Mesh/Floor",
            (50.0, 50.0, 0.0),
            "ground",
        ),
        SpawnOp(
            "gw_village_ground_1_0",
            "village:1,0",
            "/Game/Mesh/Floor",
            (150.0, 50.0, 0.0),
            "ground",
        ),
    ]
    paths = anyio.run(apply, _Fake(), plan)  # type: ignore[arg-type]
    assert spawned == ["gw_village_ground_0_0", "gw_village_ground_1_0"]
    assert paths == [
        "/Game/Maps/M.M:PersistentLevel.gw_village_ground_0_0",
        "/Game/Maps/M.M:PersistentLevel.gw_village_ground_1_0",
    ]


def test_apply_names_the_failing_op_in_the_error() -> None:
    from glyphwright.frontends.presentation.ue5.client import UE5Error
    from glyphwright.frontends.presentation.ue5.importer import SpawnOp, apply

    async def boom(
        class_path: str, *, name: str, location: tuple[float, float, float]
    ) -> str:
        raise RuntimeError("editor exploded")

    class _Fake:
        spawn_from_class = staticmethod(boom)

    plan = [
        SpawnOp(
            "gw_village_ground_7_3",
            "village:7,3",
            "/Game/Mesh/Wall",
            (750.0, 350.0, 0.0),
            "ground",
        )
    ]
    with pytest.raises(UE5Error) as caught:
        anyio.run(apply, _Fake(), plan)  # type: ignore[arg-type]
    assert "village:7,3" in str(caught.value)
    assert "gw_village_ground_7_3" in str(caught.value)
