"""Tile geometry: the first implementation of the ``Space`` protocol.

Exits derive from adjacency rather than authoring, and positions are ``(x, y)``
with ``x`` growing east and ``y`` growing south (design 0003 section 7.2). This
is the Neverwinter Nights authoring model: tile-based world description,
presentation-independent.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from glyphwright.world.space import EntityId, ExitToken, PosId, SpatialObservation

if TYPE_CHECKING:
    from glyphwright.kernel.state import WorldState

FLOOR = "."
WALL = "#"
_TERRAIN = frozenset({FLOOR, WALL})

# Ordered so exit enumeration and iteration are deterministic everywhere.
_OFFSETS: tuple[tuple[ExitToken, int, int], ...] = (
    ("north", 0, -1),
    ("east", 1, 0),
    ("south", 0, 1),
    ("west", -1, 0),
)


def _local(x: int, y: int) -> str:
    return f"{x},{y}"


def _coords(pos: PosId) -> tuple[int, int]:
    x_text, separator, y_text = pos.local.partition(",")
    if not separator:
        raise ValueError(f"not a grid position: {pos}")
    return int(x_text), int(y_text)


@dataclass(frozen=True, slots=True)
class GridSpace:
    """A rectangular tile area addressed by ``area:x,y``."""

    _area: str
    rows: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.rows or not self.rows[0]:
            raise ValueError("a grid area must not be empty")
        if any(len(row) != len(self.rows[0]) for row in self.rows):
            raise ValueError("grid rows must have equal width")
        unsupported = {c for row in self.rows for c in row} - _TERRAIN
        if unsupported:
            raise ValueError(f"unsupported terrain glyphs: {sorted(unsupported)}")

    @classmethod
    def from_text(cls, area: str, text: str) -> GridSpace:
        return cls(_area=area, rows=tuple(text.splitlines()))

    @property
    def area(self) -> str:
        return self._area

    @property
    def width(self) -> int:
        return len(self.rows[0])

    @property
    def height(self) -> int:
        return len(self.rows)

    def pos(self, x: int, y: int) -> PosId:
        """The identifier for a tile, for content and tests to name positions."""
        return PosId(area=self._area, local=_local(x, y))

    def contains(self, pos: PosId) -> bool:
        if pos.area != self._area:
            return False
        try:
            x, y = _coords(pos)
        except ValueError:
            return False
        return 0 <= x < self.width and 0 <= y < self.height

    def terrain(self, pos: PosId) -> str:
        x, y = _coords(pos)
        return self.rows[y][x]

    def positions(self) -> Iterable[PosId]:
        for y in range(self.height):
            for x in range(self.width):
                yield self.pos(x, y)

    def exits(self, pos: PosId) -> Mapping[ExitToken, PosId]:
        """Adjacent positions inside the area, by token.

        Exits are topology, not permission: a wall is still an exit token here,
        and ``passable`` is what refuses it. This keeps the command grammar a
        function of the map's shape rather than of what happens to block today,
        so an agent can attempt a move and learn *why* it failed.
        """
        x, y = _coords(pos)
        found: dict[ExitToken, PosId] = {}
        for token, dx, dy in _OFFSETS:
            neighbour = self.pos(x + dx, y + dy)
            if self.contains(neighbour):
                found[token] = neighbour
        return found

    def melee_range(self, a: PosId, b: PosId) -> bool:
        return a == b or b in self.exits(a).values()

    def passable(self, state: WorldState, pos: PosId, mover: EntityId) -> bool:
        return self.blocked_reason(state, pos, mover) is None

    def blocked_reason(
        self, state: WorldState, pos: PosId, mover: EntityId
    ) -> str | None:
        if not self.contains(pos):
            return "edge"
        if self.terrain(pos) == WALL:
            return "wall"
        blocked = any(
            entity.blocker is not None and entity.id != mover
            for entity in state.entities_at(pos)
        )
        return "occupied" if blocked else None

    def occupants(self, state: WorldState, pos: PosId) -> tuple[EntityId, ...]:
        return tuple(entity.id for entity in state.entities_at(pos))

    def observe(self, state: WorldState, observer: EntityId) -> SpatialObservation:
        origin = state.entity(observer).at()
        if origin is None:
            raise ValueError(f"{observer} has no position to observe from")
        # Slice 1 has no field-of-view filtering; the whole area is visible
        # (0003 section 20.3 defers visibility to a later slice).
        visible = tuple(self.positions())
        actors = tuple(
            sorted(
                entity.id
                for entity in state.entities.values()
                if entity.actor is not None
                and entity.id != observer
                and (at := entity.at()) is not None
                and at.area == self._area
            )
        )
        return SpatialObservation(
            area=self._area, origin=origin, visible=visible, actors=actors
        )
