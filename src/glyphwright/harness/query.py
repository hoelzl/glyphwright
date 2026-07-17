"""The oracle: stable paths over world state, never advancing the turn.

Queries answer "what is true right now" as data, and stat queries carry their
full derivation, so "why is attack 8?" is assertable rather than debuggable
(design 0003 sections 9.1 and 13). Unknown paths are error values, never
exceptions — the same contract as command rejections.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from glyphwright.effects.stats import derive
from glyphwright.world.entities import Equipment

if TYPE_CHECKING:
    from glyphwright.kernel.state import WorldState


@dataclass(frozen=True, slots=True)
class QueryResult:
    """One oracle answer: a JSON-able value, or an error as data."""

    path: str
    value: object = None
    explanation: tuple[str, ...] = ()
    error: str | None = None


def _error(path: str, reason: str) -> QueryResult:
    return QueryResult(path=path, error=reason)


def _entity_query(state: WorldState, path: str, parts: list[str]) -> QueryResult:
    entity_id = parts[0]
    if entity_id not in state.entities:
        return _error(path, "no_such_entity")
    entity = state.entity(entity_id)

    match parts[1:]:
        case ["hp"] if entity.actor is not None:
            return QueryResult(path=path, value=[entity.actor.hp, entity.actor.max_hp])
        case ["position"]:
            at = entity.at()
            return QueryResult(path=path, value=None if at is None else str(at))
        case ["inventory"]:
            return QueryResult(path=path, value=list(entity.carries()))
        case ["equipment"]:
            worn = entity.equipment or Equipment()
            return QueryResult(path=path, value=dict(worn.slots))
        case ["stats", stat]:
            derivation = derive(state, entity_id, stat)
            return QueryResult(
                path=path, value=derivation.value, explanation=derivation.explain()
            )
        case _:
            return _error(path, "no_such_path")


def query(state: WorldState, path: str) -> QueryResult:
    """Resolve one oracle path against a state."""
    match path.split("."):
        case ["world", "turn"]:
            return QueryResult(path=path, value=state.turn)
        case ["world", "mode"]:
            return QueryResult(path=path, value=state.mode)
        case ["world", "flags"]:
            return QueryResult(path=path, value=dict(state.flags))
        case ["world", "entities"]:
            return QueryResult(path=path, value=sorted(state.entities))
        case [entity_id, *rest] if rest and entity_id != "world":
            return _entity_query(state, path, [entity_id, *rest])
        case _:
            return _error(path, "no_such_path")
