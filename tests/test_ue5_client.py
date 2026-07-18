"""The UE5 MCP client: typed helpers over the editor's meta-tools (14C).

These tests inject a fake transport, so the client is verified offline; the
live editor is exercised only by the opt-in e2e mark. The fake mirrors the
confirmed round-trip shape: ``call_tool`` takes ``{toolset_name, tool_name,
arguments}`` with the bare tool name and returns ``{"returnValue": ...}`` with
nested payloads JSON-encoded as strings. Tests run the async client through
``anyio.run`` so the standard suite needs no async plugin.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable

import anyio


def run(coro: Awaitable[object]) -> object:
    return anyio.run(lambda: coro)  # type: ignore[arg-type, return-value]


async def _fake_transport(tool: str, arguments: dict[str, object]) -> object:
    assert tool == "call_tool"
    tool_name = arguments["tool_name"]
    assert isinstance(tool_name, str)
    canned = {
        "get_current_level": {"returnValue": "/Game/Maps/EmptyOpenWorld1"},
        "ListAnchors": {
            "returnValue": json.dumps(
                [{"anchorId": "A1", "worldStateKey": "great_hall", "kind": "Volume"}]
            )
        },
    }
    return canned[tool_name]


def _client(spy: object | None = None) -> "object":
    from glyphwright.frontends.presentation.ue5.client import UE5Client

    return UE5Client(spy if spy is not None else _fake_transport)  # type: ignore[arg-type]


def test_call_tool_uses_the_bare_tool_name_and_toolset() -> None:
    calls: list[dict[str, object]] = []

    async def spy(tool: str, arguments: dict[str, object]) -> object:
        calls.append(arguments)
        return {"returnValue": "/Game/Maps/M"}

    from glyphwright.frontends.presentation.ue5.client import SCENE, UE5Client

    level = run(UE5Client(spy).current_level())
    assert level == "/Game/Maps/M"
    assert calls[0]["toolset_name"] == SCENE
    assert calls[0]["tool_name"] == "get_current_level"
    assert calls[0]["arguments"] == {}


def test_current_level_unwraps_the_envelope() -> None:
    assert run(_client().current_level()) == "/Game/Maps/EmptyOpenWorld1"  # type: ignore[attr-defined]


def test_list_anchors_decodes_the_nested_json_string() -> None:
    anchors = run(_client().list_anchors())  # type: ignore[attr-defined]
    assert anchors == [{"anchorId": "A1", "worldStateKey": "great_hall", "kind": "Volume"}]


def test_spawn_passes_class_name_and_location() -> None:
    seen: list[dict[str, object]] = []

    async def spy(tool: str, arguments: dict[str, object]) -> object:
        seen.append(arguments["arguments"])  # type: ignore[index]
        return {"returnValue": json.dumps({"actor": "/Game/X.C_1"})}

    from glyphwright.frontends.presentation.ue5.client import UE5Client

    run(
        UE5Client(spy).spawn_from_class(
            "/Script/Engine.StaticMeshActor",
            name="gw_village_7_3",
            location=(700.0, 300.0, 0.0),
        )
    )
    args = seen[0]
    assert args["actor_type"] == {"refPath": "/Script/Engine.StaticMeshActor"}
    assert args["name"] == "gw_village_7_3"
    assert args["xform"]["location"] == {"x": 700.0, "y": 300.0, "z": 0.0}  # type: ignore[index]


def test_capture_viewport_poses_the_camera() -> None:
    seen: list[dict[str, object]] = []

    async def spy(tool: str, arguments: dict[str, object]) -> object:
        seen.append(arguments["arguments"])  # type: ignore[index]
        return {"returnValue": "iVBORw0KGgo="}

    from glyphwright.frontends.presentation.ue5.client import UE5Client

    run(UE5Client(spy).capture_viewport(location=(400.0, 150.0, 600.0), yaw=0.0, pitch=-90.0))
    xform = seen[0]["captureTransform"]
    assert xform["location"] == {"x": 400.0, "y": 150.0, "z": 600.0}  # type: ignore[index]
    assert xform["rotation"]["pitch"] == -90.0  # type: ignore[index]
