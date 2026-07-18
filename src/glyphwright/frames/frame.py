"""Semantic frames: the canonical observation after each step.

Frames are pure data and all frontends are pure functions over them, so raw
glyph output is derived material rather than the oracle (design 0003 section
11). Message text is generated from templates over event data, never
free-written in handlers, which keeps prose deterministic and localizable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from glyphwright.kernel.commands import CommandGrammar
from glyphwright.world.space import EntityId, PosId

if TYPE_CHECKING:
    from glyphwright.world.entities import Entity


@dataclass(frozen=True, slots=True)
class ActorSummary:
    """A visible actor, as a frame reports it.

    ``mp`` is ``None`` for an actor without a pool (``max_mp == 0``), so a
    consumer never confuses "no mana system" with "an empty pool"
    (design 0009 §4).
    """

    id: EntityId
    name: str
    hp: int
    max_hp: int
    at: PosId
    statuses: tuple[str, ...] = ()
    mp: tuple[int, int] | None = None

    @classmethod
    def of(cls, entity: Entity, at: PosId) -> ActorSummary:
        """The one construction: every mode summarises actors through here,
        so a new field cannot be forgotten in one mode's copy."""
        actor = entity.actor
        assert actor is not None, "only actors are summarised"
        return cls(
            id=entity.id,
            name=actor.name,
            hp=actor.hp,
            max_hp=actor.max_hp,
            at=at,
            statuses=entity.statuses.ids() if entity.statuses else (),
            mp=(actor.mp, actor.max_mp) if actor.max_mp else None,
        )


@dataclass(frozen=True, slots=True)
class GridView:
    """A viewport of tiles around the observer, plus its legend."""

    area: str
    origin: tuple[int, int]
    tiles: tuple[str, ...]
    legend: tuple[tuple[str, str], ...]

    kind: str = "grid"


@dataclass(frozen=True, slots=True)
class RoomView:
    """A room-graph viewport: classic IF presentation (0003 §7.3)."""

    area: str
    room: str
    name: str
    description: str
    contents: tuple[EntityId, ...]
    exits: tuple[str, ...]

    kind: str = "room"


@dataclass(frozen=True, slots=True)
class DialogueView:
    """A conversation's viewport: who speaks, what they said, the choices."""

    area: str
    speaker: EntityId
    text: str
    choices: tuple[str, ...]

    kind: str = "dialogue"


@dataclass(frozen=True, slots=True)
class LockView:
    """The lockpicking minigame's viewport (design 0003 §10.3)."""

    area: str
    target: EntityId
    pins: int
    total: int

    kind: str = "lock"


@dataclass(frozen=True, slots=True)
class MenuView:
    """A menu battle's viewport: who is in the fight (0003 §10.1).

    Combatant summaries live in the frame's ``actors``; this names who is on
    the initiative list.
    """

    area: str
    combatants: tuple[EntityId, ...]

    kind: str = "menu"


Viewport = GridView | RoomView | MenuView | DialogueView | LockView


@dataclass(frozen=True, slots=True)
class PromptSpec:
    """What input the engine expects next."""

    kind: str = "command"


@dataclass(frozen=True, slots=True)
class SemanticFrame:
    """The engine's primary observation, and TermVerify's primary evidence."""

    turn: int
    mode: str
    viewport: Viewport
    actors: tuple[ActorSummary, ...]
    messages: tuple[str, ...]
    prompt: PromptSpec
    commands: CommandGrammar
