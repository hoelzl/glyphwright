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


@dataclass(frozen=True, slots=True)
class ItemAcquired:
    """An actor picked an item up off the ground."""

    actor: EntityId
    item: EntityId
    origin: PosId

    type: str = "ItemAcquired"


@dataclass(frozen=True, slots=True)
class ItemUsed:
    """An actor used a carried consumable on a target; the item is gone."""

    actor: EntityId
    item: EntityId
    target: EntityId

    type: str = "ItemUsed"


@dataclass(frozen=True, slots=True)
class ItemEquipped:
    """An actor filled an equipment slot, possibly displacing what was there.

    A displaced item stays in the inventory it never left; ``replaced`` is
    evidence of the swap, not a second state change.
    """

    actor: EntityId
    item: EntityId
    slot: str
    replaced: EntityId | None = None

    type: str = "ItemEquipped"


@dataclass(frozen=True, slots=True)
class Healed:
    """A target recovered hit points.

    ``amount`` is what actually landed after clamping to ``max_hp``, because
    events are evidence of what happened, not of what was attempted.
    ``source`` is the item that healed, or the target itself when nothing
    else did, such as natural recovery.
    """

    target: EntityId
    amount: int
    source: EntityId

    type: str = "Healed"


@dataclass(frozen=True, slots=True)
class Provoked:
    """A hostile woke and turned on the player; it gives chase from now on."""

    actor: EntityId

    type: str = "Provoked"


@dataclass(frozen=True, slots=True)
class DamageDealt:
    """An attack landed. ``amount`` is the damage before hp clamps at zero."""

    source: EntityId
    target: EntityId
    amount: int

    type: str = "DamageDealt"


@dataclass(frozen=True, slots=True)
class AttackMissed:
    """An attack failed to hit."""

    source: EntityId
    target: EntityId

    type: str = "AttackMissed"


@dataclass(frozen=True, slots=True)
class ActorDied:
    """A non-player actor reached 0 hp and left the world."""

    actor: EntityId

    type: str = "ActorDied"


@dataclass(frozen=True, slots=True)
class Defeated:
    """The player reached 0 hp. The world survives its protagonist, so the
    player stays in it; only ``look`` is left."""

    actor: EntityId

    type: str = "Defeated"


@dataclass(frozen=True, slots=True)
class ModePushed:
    """A mode became active above the current one.

    A battle carries its initiative order: who acts after the player, in
    order.
    """

    mode: str
    initiative: tuple[EntityId, ...] = ()

    type: str = "ModePushed"


@dataclass(frozen=True, slots=True)
class ModePopped:
    """The active mode ended with an outcome: ``victory``, ``defeat``, or
    ``fled`` for a battle."""

    mode: str
    outcome: str

    type: str = "ModePopped"


@dataclass(frozen=True, slots=True)
class FleeFailed:
    """No step away would break contact; the turn is spent anyway."""

    actor: EntityId

    type: str = "FleeFailed"


Event = (
    Moved
    | MoveBlocked
    | TurnAdvanced
    | ItemAcquired
    | ItemUsed
    | ItemEquipped
    | Healed
    | Provoked
    | DamageDealt
    | AttackMissed
    | ActorDied
    | Defeated
    | ModePushed
    | ModePopped
    | FleeFailed
)
