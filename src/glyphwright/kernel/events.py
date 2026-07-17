"""Typed events: the engine's semantic evidence.

Every state change is expressed as an event, and the successor state is the fold
of the event list over the prior state (design 0003 section 5.3). Verification
targets these rather than rendered text, so events carry stable entity and
position identifiers, never screen coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass

from glyphwright.world.space import EntityId, ExitToken, PosId


@dataclass(frozen=True, slots=True)
class Moved:
    """An actor left one position and arrived at another."""

    actor: EntityId
    origin: PosId
    destination: PosId
    exit: ExitToken

    type: str = "Moved"


@dataclass(frozen=True, slots=True)
class MoveBlocked:
    """An actor attempted a move that the world refused."""

    actor: EntityId
    origin: PosId
    exit: ExitToken
    reason: str

    type: str = "MoveBlocked"


@dataclass(frozen=True, slots=True)
class TurnAdvanced:
    """The turn counter moved on."""

    turn: int

    type: str = "TurnAdvanced"


Event = Moved | MoveBlocked | TurnAdvanced
