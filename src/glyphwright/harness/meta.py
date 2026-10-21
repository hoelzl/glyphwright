"""The introspection meta channel: ``:``-prefixed commands beside the game.

A capability gate (``--harness``), not an affiliation: it is equally useful to
any harness and to a human at a prompt. Meta commands never advance the turn.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from glyphwright.effects.stats import Contribution
from glyphwright.frontends.wire import QUERY_SCHEMA, REJECTION_SCHEMA, encode_frame

if TYPE_CHECKING:
    from glyphwright.api import Engine
    from glyphwright.harness.query import QueryResult

# (command, what it does), for the help text and the generated reference.
COMMANDS: tuple[tuple[str, str], ...] = (
    (":query <path>", "answer one query path; see the paths below"),
    (":query <path> --explain", "the same, with every contribution to a stat"),
    (":seed", "the run's seed"),
    (":frame", "the current frame, in the frontend's own form"),
    (":frame --json", "the current frame as JSON"),
)
USAGE = ":query <path> [--explain] | :seed | :frame [--json]"


def encode_query_result(result: QueryResult, *, explain: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {"schema": QUERY_SCHEMA, "path": result.path}
    if result.error is not None:
        payload["error"] = result.error
        return payload
    payload["value"] = result.value
    if explain and result.explanation:
        # v2 finding N9: v0 sent prose, so an agent had to parse text to
        # check where a number came from.
        payload["explanation"] = [
            {
                "source": step.source,
                "op": step.op,
                "value": step.value,
                "running": step.running,
            }
            for step in result.explanation
        ]
    return payload


def handle(engine: Engine, line: str) -> dict[str, Any]:
    """Answer one meta command with a schema-tagged payload."""
    match line.removeprefix(":").split():
        case ["query", path]:
            return encode_query_result(engine.query(path), explain=False)
        case ["query", path, "--explain"]:
            return encode_query_result(engine.query(path), explain=True)
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
            lines = [f"{payload['path']} = {json.dumps(payload['value'])}"]
            lines.extend(
                f"  {Contribution(**step).describe()}"
                for step in payload.get("explanation", ())
            )
            return "\n".join(lines)
        case schema if schema == REJECTION_SCHEMA:
            return f"? {payload['reason']}: {payload['hint']}"
        case _:
            # Pretty-printed so each line stays short and no token is ever
            # split by a frontend's width-wrapping.
            return json.dumps(payload, indent=1, sort_keys=True)
