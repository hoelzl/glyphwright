"""The oracle fingerprint populated from a live editor (offline via fakes).

``positions_fingerprint`` is asserted directly (pure); ``oracle_fingerprint``
runs through a ``UE5Client`` whose fake transport scripts the three calls it
makes (``get_current_level``, ``describe_toolset``, ``ListAnchors``), so the
whole builder is verified without an editor. The live round-trip is the opt-in
``ue5`` e2e.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable

import pytest

pytest.importorskip("anyio")
import anyio  # noqa: E402

from glyphwright.frontends.presentation.ue5.client import ANCHOR, SCENE, UE5Client
from glyphwright.frontends.presentation.ue5.oracle import (
    oracle_fingerprint,
    positions_fingerprint,
)
from glyphwright.harness.fingerprint import OracleFingerprint


def run[T](coro: Awaitable[T]) -> T:
    async def go() -> T:
        return await coro

    return anyio.run(go)


def test_positions_fingerprint_is_order_independent_and_set_based() -> None:
    a = positions_fingerprint(["great_hall", "cellar", "tower"])
    b = positions_fingerprint(["tower", "great_hall", "cellar"])
    assert a == b
    # Duplicates collapse (it is a set fingerprint).
    assert positions_fingerprint(["x", "x", "y"]) == positions_fingerprint(["y", "x"])
    assert a.startswith("sha256:")
    # A different set hashes differently.
    assert positions_fingerprint(["great_hall"]) != a


def _scripted_client(
    *,
    level: str,
    version: str,
    anchors: list[dict[str, object]],
) -> UE5Client:
    async def transport(tool: str, arguments: dict[str, object]) -> object:
        if tool == "describe_toolset":
            assert arguments["toolset_name"] == ANCHOR
            return {"name": ANCHOR, "version": version, "tools": []}
        assert tool == "call_tool"
        toolset, tool_name = arguments["toolset_name"], arguments["tool_name"]
        if (toolset, tool_name) == (SCENE, "get_current_level"):
            return {"returnValue": json.dumps(level)}
        if (toolset, tool_name) == (ANCHOR, "ListAnchors"):
            return {"returnValue": json.dumps(anchors)}
        raise AssertionError(f"unexpected call: {toolset}.{tool_name}")

    return UE5Client(transport)


def test_oracle_fingerprint_populates_level_plugin_and_positions() -> None:
    client = _scripted_client(
        level="/Game/Maps/Village",
        version="1.0",
        anchors=[
            {"worldStateKey": "great_hall"},
            {"worldStateKey": "cellar"},
            {"worldStateKey": "great_hall"},  # duplicate collapses
        ],
    )
    fp = run(oracle_fingerprint(client))
    assert fp == OracleFingerprint(
        level="/Game/Maps/Village",
        plugin="1.0",
        positions=positions_fingerprint(["great_hall", "cellar"]),
    )


def test_oracle_fingerprint_ignores_anchors_without_a_world_state_key() -> None:
    client = _scripted_client(
        level="/Game/Maps/Village",
        version="1.0",
        anchors=[{"worldStateKey": "hall"}, {"note": "no key"}],
    )
    fp = run(oracle_fingerprint(client))
    assert fp.positions == positions_fingerprint(["hall"])


def test_positions_fingerprint_of_the_empty_set_is_well_formed() -> None:
    # A map with zero bound positions hashes to the sha256 of the empty string
    # — a conscious, valid fingerprint (0012 §11.5 hashes the *set*, which may
    # be empty), not an error.
    empty = positions_fingerprint([])
    assert empty.startswith("sha256:")
    assert empty == positions_fingerprint([])
    assert empty != positions_fingerprint(["anything"])


def test_an_empty_world_state_key_binds_no_position() -> None:
    # A present-but-empty key binds no position, so it is dropped exactly like
    # an absent one — pinned so the absent/empty conflation is deliberate.
    client = _scripted_client(
        level="/Game/Maps/Village",
        version="1.0",
        anchors=[{"worldStateKey": ""}, {"worldStateKey": "hall"}],
    )
    fp = run(oracle_fingerprint(client))
    assert fp.positions == positions_fingerprint(["hall"])


def test_describe_toolset_unwraps_an_enveloped_descriptor() -> None:
    # The meta-tools return descriptors unwrapped today, but describe_toolset
    # routes through _decode so a future build that wraps the payload (the
    # {"returnValue": ...} envelope call_tool uses) still resolves the version.
    async def wrapped(tool: str, arguments: dict[str, object]) -> object:
        assert tool == "describe_toolset"
        return {"returnValue": json.dumps({"name": ANCHOR, "version": "2.5"})}

    client = UE5Client(wrapped)
    assert run(client.describe_toolset(ANCHOR))["version"] == "2.5"


def test_describe_toolset_rejects_a_versionless_payload() -> None:
    from glyphwright.frontends.presentation.ue5.client import UE5Error

    async def versionless(tool: str, arguments: dict[str, object]) -> object:
        return {"name": ANCHOR, "tools": []}

    client = UE5Client(versionless)
    with pytest.raises(UE5Error, match="no version"):
        run(client.describe_toolset(ANCHOR))
