"""The UE5 host against a live editor: the opt-in e2e (design 0012 §9, 14C).

These tests are **never part of the standard suite.** They require a running
Unreal Editor with the MCP plugin, named by ``GLYPHWRIGHT_UE5_URL`` (default
``http://127.0.0.1:8000/mcp``); without it they skip, so CI — which has no
editor — is unaffected. Run them on demand against the local editor::

    GLYPHWRIGHT_UE5_URL=http://127.0.0.1:8000/mcp \\
        uv --no-config run pytest -m ue5 -q

They verify the real round-trip the design's §8 probe established by hand:
scene query (current level, semantic anchors), a spawn + remove through the
importer, and a posed viewport capture as the human-facing pixel evidence.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

# Like the GUI tests, these need the `ue5` extra (which pulls in ``anyio`` via
# ``mcp``); skip cleanly without it so the bare CI job passes.
pytest.importorskip("anyio")

import anyio  # noqa: E402

if TYPE_CHECKING:
    from glyphwright.frontends.presentation.ue5.client import LiveSession

pytestmark = [
    pytest.mark.ue5,
    pytest.mark.skipif(
        os.environ.get("GLYPHWRIGHT_UE5_URL") is None,
        reason="GLYPHWRIGHT_UE5_URL not set; no live editor to test against",
    ),
]

URL = os.environ.get("GLYPHWRIGHT_UE5_URL", "http://127.0.0.1:8000/mcp")


def _client_ctx() -> LiveSession:
    import importlib.util

    if importlib.util.find_spec("mcp") is None:
        pytest.skip("ue5 extra not installed")
    from glyphwright.frontends.presentation.ue5.client import LiveSession, connect

    session = connect(URL)
    assert isinstance(session, LiveSession)
    return session


def test_live_editor_reports_its_level() -> None:
    async def go() -> str:
        async with _client_ctx() as client:
            return await client.current_level()

    level = anyio.run(go)
    assert level.startswith("/Game/"), f"unexpected level path: {level}"


def test_live_editor_lists_semantic_anchors() -> None:
    async def go() -> list[dict[str, object]]:
        async with _client_ctx() as client:
            return await client.list_anchors()

    anchors = anyio.run(go)
    assert isinstance(anchors, list)
    # Every anchor carries the world-state binding the design relies on.
    for anchor in anchors:
        assert "worldStateKey" in anchor


def test_importer_spawns_and_removes_an_actor() -> None:
    async def go() -> str:
        async with _client_ctx() as client:
            actor_path = await client.spawn_from_class(
                "/Script/Engine.StaticMeshActor",
                name="gw_e2e_probe",
                location=(0.0, 0.0, 0.0),
            )
            assert actor_path.startswith("/Game/"), actor_path
            await client.remove(actor_path)
            return actor_path

    path = anyio.run(go)
    assert "StaticMeshActor" in path


def test_capture_viewport_returns_png_bytes() -> None:
    async def go() -> bytes:
        async with _client_ctx() as client:
            return await client.capture_viewport(
                location=(400.0, 150.0, 600.0), yaw=0.0, pitch=-90.0
            )

    data = anyio.run(go)
    assert data.startswith(b"\x89PNG"), "capture did not decode to a PNG"


def test_oracle_fingerprint_populates_from_the_live_editor() -> None:
    """A Tier-2 oracle fingerprint built from the live editor is well-formed
    and produces a valid session/2 header (0012 §6)."""
    from glyphwright.frontends.presentation.ue5.oracle import oracle_fingerprint
    from glyphwright.harness.fingerprint import OracleFingerprint, RunFingerprint

    async def go() -> tuple[OracleFingerprint, dict[str, object]]:
        async with _client_ctx() as client:
            fp = await oracle_fingerprint(client)
            run_fp = RunFingerprint(
                engine="glyphwright 0.0.0",
                pack="reference-vale@sha256:0",
                seed=7,
                turn=0,
                oracle=fp,
            )
            return fp, run_fp.header(harness=False)

    fp, header = anyio.run(go)
    assert isinstance(fp.level, str) and fp.level.startswith("/Game/")
    assert fp.plugin, "toolset version must be non-empty"
    assert fp.positions.startswith("sha256:")
    # The populated oracle term rides the header under session/2.
    assert header["schema"] == "glyphwright.session/2"
    oracle = header["oracle"]
    assert isinstance(oracle, dict)
    assert oracle["level"] == fp.level
    assert oracle["plugin"] == fp.plugin
    assert oracle["positions"] == fp.positions
    # And the live-populated oracle object matches the session/2 schema's
    # declared oracle shape (level/plugin/positions, all required strings,
    # nothing else) — so a drift between as_dict() and the schema fails here,
    # not just a round-trip of its own input. The full header is schema-checked
    # offline in test_wire.py; this pins the live fingerprint against the same
    # declared oracle object.
    from glyphwright.harness.schema import session_schema

    oracle_spec = session_schema()["properties"]["oracle"]
    assert set(oracle) == set(oracle_spec["required"])
    assert set(oracle) == set(oracle_spec["properties"])
    assert all(isinstance(v, str) for v in oracle.values())


def test_drift_audit_flags_a_blocked_edge_and_clears_when_removed() -> None:
    """The drift audit against a live editor: a collision cube across an edge
    is flagged as drift; once removed, the edge reads clear (0012 §11.5)."""
    from glyphwright.frontends.presentation.manifest import PresentationManifest
    from glyphwright.frontends.presentation.ue5.audit import audit
    from glyphwright.world.grid import GridSpace

    async def go() -> tuple[int, int]:
        grid = GridSpace.from_text("room", "..")
        manifest = PresentationManifest(
            bindings={}, decoration={}, hints={"tile_size_cm": 100.0}
        )
        async with _client_ctx() as client:
            # A thin wall at x=100 blocks the (0,0)-(1,0) edge (centers 50,150).
            wall = await client.call(
                "editor_toolset.toolsets.scene.SceneTools",
                "add_to_scene_from_asset",
                asset_path="/Engine/BasicShapes/Cube.Cube",
                name="gw_e2e_drift_wall",
                xform={
                    "location": {"x": 100.0, "y": 50.0, "z": 50.0},
                    "scale": {"x": 0.2, "y": 2.0, "z": 2.0},
                },
            )
            assert isinstance(wall, dict) and "refPath" in wall
            try:
                blocked = await audit(client, grid, manifest, probe_height=50.0)
            finally:
                await client.remove(str(wall["refPath"]))
            cleared = await audit(client, grid, manifest, probe_height=50.0)
            return len(blocked), len(cleared)

    blocked, cleared = anyio.run(go)
    assert blocked == 1, "the wall across the edge was not flagged as drift"
    assert cleared == 0, "the edge still reads blocked after the wall was removed"
