"""The MCP client to a running Unreal Editor (design 0012 §8, slice 14C).

The editor fronts ~60 toolsets behind three meta-tools (``list_toolsets``,
``describe_toolset``, ``call_tool``). ``UE5Client`` wraps exactly that surface
with typed helpers for the calls the importer and preview make. The transport
is injectable: production connects over streamable-HTTP; tests substitute an
in-memory transport, so the whole client is verifiable offline. The editor
round-trip shape — ``call_tool`` takes ``{toolset_name, tool_name,
arguments}`` with the *bare* tool name and returns ``{"returnValue": ...}`` —
was confirmed against the owner's UE 5.8 instance (2026-07-19).
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Awaitable, Callable
from typing import Any

#: A transport: (tool, arguments) -> the decoded JSON-RPC result payload.
#: The default connects to a live editor; tests inject a fake.
Transport = Callable[[str, dict[str, object]], Awaitable[object]]

SCENE = "editor_toolset.toolsets.scene.SceneTools"
APP = "EditorToolset.EditorAppToolset"
ANCHOR = "AgentWorldEditor.AgentWorldToolset"


class UE5Error(Exception):
    """An MCP call to the editor failed, with the tool and the report."""


def _decode(payload: object, *, tool: str, _depth: int = 0) -> object:
    """Unwrap the editor's ``{"returnValue": ...}`` envelope.

    ``call_tool`` results arrive as MCP text content carrying a JSON object
    with a single ``returnValue``; nested tool payloads are themselves JSON
    strings (e.g. ``ListAnchors`` returns a JSON array as a string), so this
    unwraps recursively until a non-string value remains. The recursion is
    depth-capped so a re-encoded envelope from a misbehaving endpoint surfaces
    as a :class:`UE5Error` rather than a ``RecursionError``.
    """
    if _depth > 8:
        raise UE5Error(f"{tool}: returnValue nested too deeply to decode")
    if isinstance(payload, dict) and set(payload) == {"returnValue"}:
        return _decode(payload["returnValue"], tool=tool, _depth=_depth + 1)
    if isinstance(payload, str):
        try:
            return _decode(json.loads(payload), tool=tool, _depth=_depth + 1)
        except json.JSONDecodeError:
            return payload
    return payload


class UE5Client:
    """A thin, typed client over the editor's three meta-tools."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def call(self, toolset: str, tool: str, **arguments: object) -> object:
        """Call ``toolset.tool`` and return the decoded payload."""
        payload = await self._transport(
            "call_tool",
            {"toolset_name": toolset, "tool_name": tool, "arguments": arguments},
        )
        return _decode(payload, tool=f"{toolset}.{tool}")

    async def current_level(self) -> str:
        """The loaded level's path (``/Game/Maps/...``)."""
        value = await self.call(SCENE, "get_current_level")
        if not isinstance(value, str) or not value:
            raise UE5Error(
                f"get_current_level returned a non-string payload: {value!r}"
            )
        return value

    async def list_anchors(self) -> list[dict[str, object]]:
        """Semantic anchors on actors in loaded cells (world-state bindings)."""
        value = await self.call(ANCHOR, "ListAnchors")
        if not isinstance(value, list):
            raise UE5Error(f"ListAnchors returned a non-list payload: {value!r}")
        return value

    async def spawn_from_class(
        self,
        class_path: str,
        *,
        name: str,
        location: tuple[float, float, float],
    ) -> str:
        """Spawn an actor of a native class at a world location.

        Returns the spawned actor's full soft path (``/Game/Maps/...``), which
        is the handle :meth:`remove` and anchor queries need — confirmed against
        the live editor, which answers ``{"refPath": ...}``.
        """
        result = await self.call(
            SCENE,
            "add_to_scene_from_class",
            actor_type={"refPath": class_path},
            name=name,
            xform={"location": {"x": location[0], "y": location[1], "z": location[2]}},
        )
        if isinstance(result, dict) and "refPath" in result:
            return str(result["refPath"])
        return str(result)

    async def remove(self, actor_path: str) -> object:
        """Remove an actor by its full soft path (the spawn's return value)."""
        return await self.call(
            SCENE, "remove_from_scene", actor={"refPath": actor_path}
        )

    async def trace_world(
        self,
        start: tuple[float, float, float],
        end: tuple[float, float, float],
    ) -> float | None:
        """A collision trace from ``start`` to ``end``.

        Returns the distance from ``start`` to the first hit, or ``None`` when
        the ray reaches ``end`` unobstructed. This is the drift-detection
        oracle's primitive (0012 §11.5): a ray between two grid cells the pack
        calls passable should return ``None`` (or the full distance); a shorter
        hit means geometry blocks an edge the semantics expect to be open. Only
        geometry with a collision mesh registers (live finding, 2026-07-19).
        """
        result = await self.call(
            SCENE,
            "trace_world",
            start={"x": start[0], "y": start[1], "z": start[2]},
            end={"x": end[0], "y": end[1], "z": end[2]},
        )
        if result is None:
            return None
        return float(result)  # type: ignore[arg-type]

    async def capture_viewport(
        self, *, location: tuple[float, float, float], yaw: float, pitch: float
    ) -> bytes:
        """A viewport capture from a posed camera, as PNG bytes.

        The editor answers ``{"image": {"mimeType", "data"}}`` with base64
        data and requires an (empty) ``annotations`` object; both are live
        findings (2026-07-19). Returns the decoded bytes.
        """
        import base64

        result = await self.call(
            APP,
            "CaptureViewport",
            captureTransform={
                "location": {"x": location[0], "y": location[1], "z": location[2]},
                "rotation": {"pitch": pitch, "yaw": yaw, "roll": 0.0},
            },
            annotations={},
        )
        if isinstance(result, dict) and "image" in result:
            image = result["image"]
            assert isinstance(image, dict)
            return base64.b64decode(str(image["data"]))
        return base64.b64decode(str(result))


def connect(url: str) -> LiveSession:
    """Prepare a live session to a running editor at ``url`` (streamable-HTTP).

    Returns a context manager owning the connection; ``async with`` it to get a
    transport-bound :class:`UE5Client`. Deferred imports keep ``mcp`` out of
    the core. Construction is synchronous — only entering the context opens
    the connection.
    """
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    return LiveSession(streamablehttp_client, ClientSession, url)


class LiveSession:
    """Owns one MCP connection; yields a transport-bound :class:`UE5Client`."""

    def __init__(
        self,
        http_client: Callable[..., object],
        session_cls: Callable[..., object],
        url: str,
    ) -> None:
        self._http_client = http_client
        self._session_cls = session_cls
        self._url = url
        self._stack: contextlib.AsyncExitStack | None = None
        self._session: Any = None

    async def __aenter__(self) -> UE5Client:
        stack = contextlib.AsyncExitStack()
        # The ``mcp`` client's context-manager and session types are looser
        # than strict mode admits; the boundary is deliberately ``Any`` (the
        # plugin is Experimental — 0012 §8), with the shapes pinned by the
        # opt-in e2e against a live editor.
        try:
            http: Any = self._http_client
            session_cls: Any = self._session_cls
            read, write, _ = await stack.enter_async_context(http(self._url))
            session: Any = await stack.enter_async_context(session_cls(read, write))
            await session.initialize()
        except BaseException:
            # A failed enter must not leak the partially-entered transports.
            await stack.aclose()
            raise
        self._stack = stack
        self._session = session
        return UE5Client(self._transport)

    async def __aexit__(self, *exc: object) -> None:
        stack, self._stack = self._stack, None
        if stack is not None:
            await stack.aclose()

    async def _transport(self, tool: str, arguments: dict[str, object]) -> object:
        result = await self._session.call_tool(tool, arguments)
        texts = [c.text for c in result.content if getattr(c, "type", None) == "text"]
        if getattr(result, "isError", False):
            raise UE5Error(f"{tool}: {' '.join(texts)}")
        return json.loads(texts[0]) if texts else None
