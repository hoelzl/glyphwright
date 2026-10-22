"""Queries: stable paths over world state, never advancing the turn.

Queries answer "what is true right now" as data, and stat queries carry their
full derivation, so "why is attack 8?" is assertable rather than debuggable.
Unknown paths are error values, never exceptions: the same contract as
command rejections.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from glyphwright.effects.stats import Contribution, derive
from glyphwright.world.entities import Equipment

if TYPE_CHECKING:
    from glyphwright.kernel.state import WorldState

# What :query answers, for the generated command reference.
PATHS: tuple[tuple[str, str], ...] = (
    ("world.turn", "the current turn"),
    ("world.mode", "the active mode"),
    ("world.entities", "every entity id, sorted"),
    ("world.initiative", "the battle's initiative order; empty outside a battle"),
    ("<id>.hp", "an actor's hp as [current, maximum]"),
    ("<id>.position", "where the entity stands, or null"),
    ("<id>.inventory", "the item ids it carries, in the order taken"),
    ("<id>.equipment", "its slots, as slot to item id"),
    ("<id>.stats.<stat>", "a stat's value; --explain adds every contribution"),
)
ERRORS: tuple[tuple[str, str], ...] = (
    ("no_such_entity", "no entity has that id"),
    (
        "no_such_path",
        "the path is not one of the paths above, or asks an actor's `hp` or "
        "`stats` of an entity that is not an actor, such as an item",
    ),
    ("no_such_stat", "the entity neither has nor is modified in that stat"),
)


@dataclass(frozen=True, slots=True)
class QueryResult:
    """One answer: a JSON-able value with its derivation, or an error as data."""

    path: str
    value: object = None
    explanation: tuple[Contribution, ...] = ()
    error: str | None = None


def _error(path: str, reason: str) -> QueryResult:
    return QueryResult(path=path, error=reason)


def _known_stats(state: WorldState, entity_id: str) -> set[str]:
    """The stats an entity declares: base stats plus anything worn modifies."""
    entity = state.entity(entity_id)
    known = {name for name, _ in entity.actor.base_stats} if entity.actor else set()
    if entity.equipment is not None:
        for _, item_id in entity.equipment.slots:
            equippable = state.entity(item_id).equippable
            if equippable is not None:
                known.update(modifier.stat for modifier in equippable.modifiers)
    return known


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
            if entity.actor is None:
                return _error(path, "no_such_path")
            if stat not in _known_stats(state, entity_id):
                # Deriving an undeclared stat would fabricate a confident 0;
                # a query answers what is true or says why it cannot.
                return _error(path, "no_such_stat")
            derivation = derive(state, entity_id, stat)
            return QueryResult(
                path=path, value=derivation.value, explanation=derivation.contributions
            )
        case _:
            return _error(path, "no_such_path")


def query(state: WorldState, path: str) -> QueryResult:
    """Resolve one query path against a state."""
    match path.split("."):
        case ["world", "turn"]:
            return QueryResult(path=path, value=state.turn)
        case ["world", "mode"]:
            return QueryResult(path=path, value=state.mode)
        case ["world", "entities"]:
            return QueryResult(path=path, value=sorted(state.entities))
        case ["world", "initiative"]:
            return QueryResult(path=path, value=list(state.initiative))
        case [entity_id, *rest] if rest and entity_id != "world":
            return _entity_query(state, path, [entity_id, *rest])
        case _:
            return _error(path, "no_such_path")
