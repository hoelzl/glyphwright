"""The introspection meta channel: ``:``-prefixed commands beside the game.

A capability gate (``--harness``), not an affiliation: it is equally useful to
any harness and to a human at a prompt. Meta commands never advance the turn.
S1 answers ``:seed`` and ``:frame``; ``:query`` arrives with stats in S3.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from glyphwright.frontends.wire import QUERY_SCHEMA, REJECTION_SCHEMA, encode_frame

if TYPE_CHECKING:
    from glyphwright.api import Engine

USAGE = ":seed | :frame [--json]"


def handle(engine: Engine, line: str) -> dict[str, Any]:
    """Answer one meta command with a schema-tagged payload."""
    match line.removeprefix(":").split():
        case ["seed"]:
            return {
                "schema": QUERY_SCHEMA,
                "path": "seed",
                "value": engine.fingerprint().seed,
            }
        case ["frame"] | ["frame", "--json"]:
            return encode_frame(engine.frame())
        case _:
            return {
                "schema": REJECTION_SCHEMA,
                "turn": engine.frame().turn,
                "command": line,
                "reason": "unknown_meta",
                "hint": USAGE,
            }


def render_text(payload: dict[str, Any]) -> str:
    """The plain frontend's rendering of a meta payload."""
    match payload["schema"]:
        case schema if schema == QUERY_SCHEMA:
            if "error" in payload:
                return f"? {payload['error']}: {payload['path']}"
            return f"{payload['path']} = {json.dumps(payload['value'])}"
        case schema if schema == REJECTION_SCHEMA:
            return f"? {payload['reason']}: {payload['hint']}"
        case _:
            # Pretty-printed so each line stays short and no token is ever
            # split by a frontend's width-wrapping.
            return json.dumps(payload, indent=1, sort_keys=True)
