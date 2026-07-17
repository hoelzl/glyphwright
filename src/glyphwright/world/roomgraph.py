"""Room-graph geometry: the second implementation of the ``Space`` protocol.

``PosId`` is an opaque room id and exits are authored, one-way in data —
reverse links are authored explicitly (design 0003 section 7.3). This is
classic IF presentation: room prose, contents, exit list.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from glyphwright.world.space import EntityId, ExitToken, PosId, SpatialObservation

if TYPE_CHECKING:
    from glyphwright.kernel.state import WorldState


@dataclass(frozen=True, slots=True)
class Room:
    """One authored room: identity, prose, and its outgoing exits."""

    id: str
    name: str
    description: str
    exits: tuple[tuple[ExitToken, str], ...]


@dataclass(frozen=True, slots=True)
class RoomGraphSpace:
    """An area of authored rooms, addressed by ``area:room-id``."""

    _area: str
    rooms: tuple[Room, ...]

    def __post_init__(self) -> None:
        if not self.rooms:
            raise ValueError("a room area must contain at least one room")
        ids = [room.id for room in self.rooms]
        if len(ids) != len(set(ids)):
            raise ValueError("room ids must be unique within an area")
        for room in self.rooms:
            tokens = [token for token, _ in room.exits]
            if len(tokens) != len(set(tokens)):
                raise ValueError(f"room {room.id!r} declares a duplicate exit token")
            for token, destination in room.exits:
                if destination not in ids:
                    raise ValueError(
                        f"room {room.id!r} exit {token!r} leads to unknown "
                        f"room {destination!r}"
                    )
            for prose in (room.name, room.description):
                # Transcript-safe prose: the plain frontend delimits room
                # blocks structurally, so prose must not imitate its markup.
                if "\n" in prose:
                    raise ValueError(f"room {room.id!r} prose must be single-line")
                if prose.startswith(("Exits: ", "* ", "== ", "| ", "% ")):
                    raise ValueError(
                        f"room {room.id!r} prose must not imitate transcript markup"
                    )

    @property
    def area(self) -> str:
        return self._area

    def pos(self, room_id: str) -> PosId:
        return PosId(area=self._area, local=room_id)

    def room(self, pos: PosId) -> Room:
        for room in self.rooms:
            if room.id == pos.local:
                return room
        raise KeyError(f"no such room: {pos}")

    def contains(self, pos: PosId) -> bool:
        return pos.area == self._area and any(r.id == pos.local for r in self.rooms)

    def positions(self) -> Iterable[PosId]:
        for room in self.rooms:
            yield self.pos(room.id)

    def exits(self, pos: PosId) -> Mapping[ExitToken, PosId]:
        return {
            token: self.pos(destination) for token, destination in self.room(pos).exits
        }

    def melee_range(self, a: PosId, b: PosId) -> bool:
        # A neighbouring room is behind a wall, not at arm's length.
        return a == b

    def passable(self, state: WorldState, pos: PosId, mover: EntityId) -> bool:
        return self.blocked_reason(state, pos, mover) is None

    def blocked_reason(
        self, state: WorldState, pos: PosId, mover: EntityId
    ) -> str | None:
        # Rooms hold many occupants; bodies do not fill a room, so occupancy
        # never blocks here. Room-scale blocking arrives with closed/locked
        # exits ("closed", 0003 §7.1), gated by flags.
        if not self.contains(pos):
            return "edge"
        return None

    def occupants(self, state: WorldState, pos: PosId) -> tuple[EntityId, ...]:
        return tuple(entity.id for entity in state.entities_at(pos))

    def observe(self, state: WorldState, observer: EntityId) -> SpatialObservation:
        origin = state.entity(observer).at()
        if origin is None:
            raise ValueError(f"{observer} has no position to observe from")
        actors = tuple(
            sorted(
                entity.id
                for entity in state.entities.values()
                if entity.actor is not None
                and entity.id != observer
                and (at := entity.at()) is not None
                and at == origin
            )
        )
        return SpatialObservation(
            area=self._area, origin=origin, visible=(origin,), actors=actors
        )
