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


@dataclass(frozen=True, slots=True)
class ItemAcquired:
    """An actor picked an item up off the ground."""

    actor: EntityId
    item: EntityId
    origin: PosId

    type: str = "ItemAcquired"


@dataclass(frozen=True, slots=True)
class ItemUsed:
    """An actor used a carried item on a target.

    ``consumed`` records whether the item was destroyed by the use; the fold
    removes consumed items from the world.
    """

    actor: EntityId
    item: EntityId
    target: EntityId
    consumed: bool

    type: str = "ItemUsed"


@dataclass(frozen=True, slots=True)
class ItemEquipped:
    """An actor filled an equipment slot, possibly displacing what was there.

    A displaced item returns to the inventory it never left; ``replaced`` is
    evidence of the swap, not a second state change.
    """

    actor: EntityId
    item: EntityId
    slot: str
    replaced: EntityId | None

    type: str = "ItemEquipped"


@dataclass(frozen=True, slots=True)
class Healed:
    """A target recovered hit points.

    ``amount`` is what actually landed after clamping to ``max_hp``, because
    events are evidence of what happened, not of what was attempted.
    """

    target: EntityId
    amount: int
    source: EntityId

    type: str = "Healed"


Event = (
    Moved | MoveBlocked | TurnAdvanced | ItemAcquired | ItemUsed | ItemEquipped | Healed
)
