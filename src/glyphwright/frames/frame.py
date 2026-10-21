"""Semantic frames: the canonical observation after each step.

Frames are pure data and all frontends are pure functions over them, so raw
glyph output is derived material rather than the evidence. Message text is
generated from templates over event data, never free-written in handlers,
which keeps prose deterministic and localizable.
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
    """A visible actor, as a frame reports it."""

    id: EntityId
    name: str
    hp: int
    max_hp: int
    at: PosId

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
        )


@dataclass(frozen=True, slots=True)
class Cell:
    """One grid position's compositing tiers.

    A cell is not one glyph but three: the ``ground`` terrain (always present),
    an optional ``fixture`` (an item or furnishing drawn on the ground), and an
    optional ``actor`` (drawn over both). The frame carries the tiers so "the
    floor persists under the player" is a fact of the evidence, not something a
    frontend must reconstruct.
    """

    ground: str
    fixture: str | None = None
    actor: str | None = None


@dataclass(frozen=True, slots=True)
class GridView:
    """A viewport of tiered cells around the observer, plus its legend.

    ``cells[y][x]`` is the composited tile at that viewport position. Use
    :func:`flatten` to project the tiers back to a single-glyph surface with
    the declared precedence actor > fixture > ground.
    """

    area: str
    origin: tuple[int, int]
    cells: tuple[tuple[Cell, ...], ...]
    legend: tuple[tuple[str, str], ...]

    kind: str = "grid"


def flatten(viewport: GridView) -> tuple[str, ...]:
    """Project a tiered grid back to one glyph per cell.

    Single-glyph surfaces cannot draw a stack, so they take the topmost tier:
    actor over fixture over ground. The precedence is declared here once, not
    re-derived per frontend.
    """
    return tuple(
        "".join(cell.actor or cell.fixture or cell.ground for cell in row)
        for row in viewport.cells
    )


# Later viewports (a battle menu) join this union.
Viewport = GridView


@dataclass(frozen=True, slots=True)
class PromptSpec:
    """What input the engine expects next."""

    kind: str = "command"


@dataclass(frozen=True, slots=True)
class SemanticFrame:
    """The engine's primary observation, and a verifier's primary evidence."""

    turn: int
    mode: str
    viewport: Viewport
    actors: tuple[ActorSummary, ...]
    messages: tuple[str, ...]
    prompt: PromptSpec
    commands: CommandGrammar
