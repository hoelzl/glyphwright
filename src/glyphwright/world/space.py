"""Position identity and the protocol every world geometry implements.

Grid worlds and room worlds implement one protocol rather than emulating each
other, so ``move <exit-token>`` is the only movement command anywhere (design
0003 section 7.1).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from glyphwright.kernel.state import WorldState

EntityId = str
ExitToken = str


@dataclass(frozen=True, slots=True, order=True)
class PosId:
    """A stable, area-qualified position identifier such as ``village:7,3``.

    Positions in events, frames, and queries are semantic identifiers, never
    screen coordinates, so assertions survive rendering changes (0003 section
    7.5). ``local`` is opaque to everything outside the owning space.
    """

    area: str
    local: str

    def __str__(self) -> str:
        return f"{self.area}:{self.local}"

    @classmethod
    def parse(cls, text: str) -> PosId:
        area, separator, local = text.partition(":")
        if not separator or not area or not local:
            raise ValueError(f"malformed position identifier: {text!r}")
        return cls(area=area, local=local)


@dataclass(frozen=True, slots=True)
class SpatialObservation:
    """What an observer can currently perceive of its surroundings."""

    area: str
    origin: PosId
    visible: tuple[PosId, ...]
    actors: tuple[EntityId, ...]


@runtime_checkable
class Space(Protocol):
    """One area's topology.

    Spaces are immutable descriptions of terrain and connectivity. Anything that
    depends on who or what currently occupies a position takes the world state,
    because occupancy lives in the entity table rather than in the geometry.
    """

    @property
    def area(self) -> str:
        """The area identifier this space qualifies its positions with."""

    def positions(self) -> Iterable[PosId]:
        """Every position in the area, in a deterministic order."""

    def exits(self, pos: PosId) -> Mapping[ExitToken, PosId]:
        """Traversable exit tokens leading out of ``pos``, ignoring occupancy."""

    def passable(self, state: WorldState, pos: PosId, mover: EntityId) -> bool:
        """Whether ``mover`` may enter ``pos`` given the current state."""

    def blocked_reason(
        self, state: WorldState, pos: PosId, mover: EntityId
    ) -> str | None:
        """Why ``mover`` may not enter ``pos``, or ``None`` if it may.

        Each geometry names its own obstructions — a grid says ``wall``, a room
        graph will say ``closed`` — so modes can report *why* a move failed
        without knowing which kind of space they are standing in.
        """

    def occupants(self, state: WorldState, pos: PosId) -> tuple[EntityId, ...]:
        """Entities currently at ``pos``, in deterministic order."""

    def observe(self, state: WorldState, observer: EntityId) -> SpatialObservation:
        """What ``observer`` perceives from where it stands."""
