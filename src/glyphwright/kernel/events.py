"""Typed events: the engine's semantic evidence.

Every state change is expressed as an event, and the successor state is the fold
of the event list over the prior state. Verification targets these rather than
rendered text, so events carry stable entity and position identifiers, never
screen coordinates.
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
    """The turn counter moved on, closing the round.

    ``rng`` is the encoded RNG cursor after every draw of the round; the fold
    applies it, so the successor state, cursor included, is exactly the fold of
    the events, and replay from a log cannot drift from snapshot and restore.
    Handlers construct this event without the cursor; ``step`` stamps it once
    the round's last draw is known.
    """

    turn: int
    rng: str | None = None

    type: str = "TurnAdvanced"


Event = Moved | MoveBlocked | TurnAdvanced
