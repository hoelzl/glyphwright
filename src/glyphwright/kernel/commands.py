"""Semantic commands and typed rejections.

Kernel commands are intents, not keystrokes. Every frontend translates its
input into this same language, so an agent on the JSONL stream and a human at a
prompt speak identically.
"""

from __future__ import annotations

from dataclasses import dataclass

from glyphwright.world.space import EntityId, ExitToken


@dataclass(frozen=True, slots=True)
class Move:
    """Traverse one exit token out of the current position."""

    exit: ExitToken

    verb: str = "move"

    def args(self) -> tuple[str, ...]:
        return (self.exit,)


@dataclass(frozen=True, slots=True)
class Look:
    """Re-observe the surroundings. Does not advance the turn."""

    verb: str = "look"

    def args(self) -> tuple[str, ...]:
        return ()


@dataclass(frozen=True, slots=True)
class Wait:
    """Pass the turn deliberately."""

    verb: str = "wait"

    def args(self) -> tuple[str, ...]:
        return ()


@dataclass(frozen=True, slots=True)
class Take:
    """Pick an item up from the current position."""

    item: EntityId

    verb: str = "take"

    def args(self) -> tuple[str, ...]:
        return (self.item,)


@dataclass(frozen=True, slots=True)
class Use:
    """Use a carried consumable on yourself."""

    item: EntityId

    verb: str = "use"

    def args(self) -> tuple[str, ...]:
        return (self.item,)


@dataclass(frozen=True, slots=True)
class Equip:
    """Fill an equipment slot with a carried item."""

    item: EntityId

    verb: str = "equip"

    def args(self) -> tuple[str, ...]:
        return (self.item,)


@dataclass(frozen=True, slots=True)
class Attack:
    """Strike a foe in the battle."""

    target: EntityId

    verb: str = "attack"

    def args(self) -> tuple[str, ...]:
        return (self.target,)


@dataclass(frozen=True, slots=True)
class Flee:
    """Break away from the battle."""

    verb: str = "flee"

    def args(self) -> tuple[str, ...]:
        return ()


Command = Move | Look | Wait | Take | Use | Equip | Attack | Flee


@dataclass(frozen=True, slots=True)
class Rejected:
    """A command the engine declined, as data rather than an exception.

    Invalid commands are never exceptions: agents receive machine-readable
    feedback, and fuzzing can tell "rejected as designed" from "engine fault".
    """

    command: str
    reason: str
    hint: str


@dataclass(frozen=True, slots=True)
class CommandGrammar:
    """The verbs valid right now, with their argument domains.

    Carried in every frame so an external harness can generate valid actions at
    every state without knowing the rules.
    """

    verbs: tuple[tuple[str, tuple[tuple[str, ...], ...]], ...]

    def verb_names(self) -> tuple[str, ...]:
        return tuple(verb for verb, _ in self.verbs)

    def domains(self, verb: str) -> tuple[tuple[str, ...], ...]:
        for name, domains in self.verbs:
            if name == verb:
                return domains
        return ()
