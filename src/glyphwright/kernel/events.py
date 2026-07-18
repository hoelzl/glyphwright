"""Typed events: the engine's semantic evidence.

Every state change is expressed as an event, and the successor state is the fold
of the event list over the prior state (design 0003 section 5.3). Verification
targets these rather than rendered text, so events carry stable entity and
position identifiers, never screen coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass

from glyphwright.world.space import EntityId, ExitToken, PosId

# The flag vocabulary lives beside the FlagSet event that writes it, so every
# consumer spells flags one way.
PLAYER_DEFEATED = "player-defeated"
_AGGRO_PREFIX = "aggro:"


def aggro_flag(entity_id: EntityId) -> str:
    return f"{_AGGRO_PREFIX}{entity_id}"


def aggro_subject(flag: str) -> EntityId | None:
    """The entity an aggro flag names, or ``None`` for other flags."""
    if flag.startswith(_AGGRO_PREFIX):
        return flag.removeprefix(_AGGRO_PREFIX)
    return None


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
    applies it, so the successor state — cursor included — is exactly the fold
    of the events (0003 §5.3) and replay-from-log cannot drift from
    snapshot/restore. Handlers construct this event without the cursor;
    ``step`` stamps it once the round's last draw is known.
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


@dataclass(frozen=True, slots=True)
class DamageDealt:
    """An attack landed."""

    source: EntityId
    target: EntityId
    ability: str
    damage_type: str
    amount: int

    type: str = "DamageDealt"


@dataclass(frozen=True, slots=True)
class AttackMissed:
    """An attack was attempted and failed to land.

    Evidence of the attempt: the turn is spent and the roll advanced the RNG
    cursor, so a miss must appear in the log or replay diverges.
    """

    source: EntityId
    target: EntityId
    ability: str

    type: str = "AttackMissed"


@dataclass(frozen=True, slots=True)
class ActorDied:
    """An actor's hit points reached zero; the fold removes it from the world.

    The player never dies through this event — defeat is a world flag
    (`player-defeated`), because the world must survive its protagonist.
    """

    actor: EntityId

    type: str = "ActorDied"


@dataclass(frozen=True, slots=True)
class FlagSet:
    """A quest or world flag changed."""

    flag: str
    value: bool

    type: str = "FlagSet"


@dataclass(frozen=True, slots=True)
class ModePushed:
    """A mode took the top of the stack.

    A battle push carries the rolled initiative order, which the fold installs
    as the scheduler queue (0003 §5.5, §10).
    """

    mode: str
    initiative: tuple[EntityId, ...] = ()
    returns: tuple[tuple[EntityId, PosId], ...] = ()

    type: str = "ModePushed"


@dataclass(frozen=True, slots=True)
class ModePopped:
    """The top mode ended, with the outcome the mode beneath consumes."""

    mode: str
    outcome: str

    type: str = "ModePopped"


@dataclass(frozen=True, slots=True)
class FleeFailed:
    """A flee attempt found no way out. The turn is spent; the battle is not."""

    actor: EntityId

    type: str = "FleeFailed"


@dataclass(frozen=True, slots=True)
class FocusSet:
    """The active mode's subject and cursor changed.

    Dialogue tracks ``(speaker, node)``, lockpicking ``(chest, pins-set)`` —
    the fold installs it as :attr:`WorldState.focus`, so mode-local progress
    replays like everything else.
    """

    entity: EntityId
    detail: str

    type: str = "FocusSet"


@dataclass(frozen=True, slots=True)
class DialogueLine:
    """A speaker said something. Pure evidence; the cursor is ``FocusSet``."""

    speaker: EntityId
    text: str

    type: str = "DialogueLine"


@dataclass(frozen=True, slots=True)
class ChoiceOffered:
    """The conversation waits on a numbered choice."""

    speaker: EntityId
    choices: tuple[str, ...]

    type: str = "ChoiceOffered"


@dataclass(frozen=True, slots=True)
class PinSet:
    """A lock pin clicked into place."""

    target: EntityId
    pins: int

    type: str = "PinSet"


@dataclass(frozen=True, slots=True)
class PinSlipped:
    """The pick slipped; the lock resets."""

    target: EntityId

    type: str = "PinSlipped"


@dataclass(frozen=True, slots=True)
class StatusApplied:
    """A timed status took hold; the fold installs it on the target."""

    target: EntityId
    status: str
    expires: int

    type: str = "StatusApplied"


@dataclass(frozen=True, slots=True)
class StatusExpired:
    """A status ran out; the fold removes it."""

    target: EntityId
    status: str

    type: str = "StatusExpired"


@dataclass(frozen=True, slots=True)
class ManaSpent:
    """A cast's cost left the caster's pool; the fold decrements (design 0009)."""

    caster: EntityId
    amount: int

    type: str = "ManaSpent"


@dataclass(frozen=True, slots=True)
class ManaRestored:
    """A target recovered mana.

    ``amount`` is what actually landed after clamping to ``max_mp`` —
    events are evidence of what happened, not of what was attempted.
    """

    target: EntityId
    amount: int
    source: EntityId

    type: str = "ManaRestored"


@dataclass(frozen=True, slots=True)
class PerkGained:
    """An actor gained a permanent status (design 0003 §9.3).

    The fold appends the perk to the actor; re-gaining an owned perk is
    evidence of the attempt, not a second acquisition.
    """

    target: EntityId
    perk: str

    type: str = "PerkGained"


@dataclass(frozen=True, slots=True)
class CastFizzled:
    """A cast whose halves do not pair: a refusal by the world (0003 A.5).

    The grammar advertised ability and target independently; the world
    answers that this ability does not reach that target. The turn is spent.
    """

    caster: EntityId
    ability: str
    target: EntityId
    reason: str

    type: str = "CastFizzled"


@dataclass(frozen=True, slots=True)
class MinigameResolved:
    """A minigame reached its outcome (design 0003 §5.3)."""

    minigame: str
    outcome: str
    target: EntityId

    type: str = "MinigameResolved"


Event = (
    Moved
    | MoveBlocked
    | TurnAdvanced
    | ItemAcquired
    | ItemUsed
    | ItemEquipped
    | Healed
    | DamageDealt
    | AttackMissed
    | ActorDied
    | FlagSet
    | ModePushed
    | ModePopped
    | FleeFailed
    | FocusSet
    | DialogueLine
    | ChoiceOffered
    | PinSet
    | PinSlipped
    | MinigameResolved
    | StatusApplied
    | StatusExpired
    | PerkGained
    | ManaSpent
    | ManaRestored
    | CastFizzled
)
