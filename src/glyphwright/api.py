"""The only supported programmatic entry point.

Everything an external harness needs flows through this surface, versioned
independently of internals; nothing in ``kernel``, ``world``, ``modes``, or
``frames`` is public (design 0003 section 14).

An adapter over this API is expected to be nearly mechanical. **If an adapter
needs logic, this surface is missing something** — that is a GlyphWright bug,
not an adapter concern.
"""

from __future__ import annotations

from dataclasses import dataclass

from glyphwright import modes
from glyphwright.content.pack import ContentPack, reference_pack
from glyphwright.frames.frame import SemanticFrame
from glyphwright.harness.fingerprint import RunFingerprint
from glyphwright.harness.query import QueryResult
from glyphwright.harness.query import query as _query
from glyphwright.kernel.commands import (
    Abort,
    Attack,
    Cast,
    Choose,
    Command,
    CommandGrammar,
    Equip,
    Flee,
    Look,
    Move,
    Open,
    Pick,
    Rejected,
    Take,
    Talk,
    Use,
    Wait,
)
from glyphwright.kernel.events import PLAYER_DEFEATED, Event
from glyphwright.kernel.rng import Rng
from glyphwright.kernel.state import WorldState
from glyphwright.kernel.step import step as _step
from glyphwright.modes import exploration

__all__ = [
    "Abort",
    "Attack",
    "Cast",
    "Choose",
    "Command",
    "CommandGrammar",
    "ContentPack",
    "Engine",
    "Equip",
    "Event",
    "Flee",
    "Look",
    "Move",
    "Open",
    "Pick",
    "QueryResult",
    "Rejected",
    "RunFingerprint",
    "SemanticFrame",
    "Snapshot",
    "StepResult",
    "Take",
    "Talk",
    "Use",
    "Wait",
    "reference_pack",
]


@dataclass(frozen=True, slots=True)
class StepResult:
    """What one command produced: a frame and events, or a typed rejection."""

    frame: SemanticFrame
    events: tuple[Event, ...] = ()
    rejection: Rejected | None = None

    @property
    def accepted(self) -> bool:
        return self.rejection is None


@dataclass(frozen=True, slots=True)
class Snapshot:
    """An opaque, serializable world state.

    Snapshots are free because state is immutable: the snapshot *is* the state
    (0003 section 5.2).
    """

    _state: WorldState
    _seed: int
    _pack_id: str


class Engine:
    """A single run: content, seed, and the state that has grown from them."""

    def __init__(self, state: WorldState, seed: int, pack_id: str) -> None:
        self._state = state
        self._seed = seed
        self._pack_id = pack_id

    @classmethod
    def new(cls, pack: ContentPack, seed: int) -> Engine:
        """Begin a run from content and an explicit seed."""
        state = WorldState(
            entities={entity.id: entity for entity in pack.entities},
            areas={space.area: space for space in pack.areas},
            mode_stack=(exploration.NAME,),
            turn=0,
            rng=Rng.from_seed(seed),
            flags={},
            ability_defs={ability.id: ability for ability in pack.abilities},
            status_defs={status.id: status for status in pack.statuses},
        )
        return cls(state=state, seed=seed, pack_id=pack.pack_id)

    def step(self, command: Command) -> StepResult:
        """Apply one command.

        An invalid command is rejected as data and advances nothing.
        """
        rejection = self._validate(command)
        if rejection is not None:
            return StepResult(frame=self.frame(), rejection=rejection)

        next_state, events = _step(self._state, command, self._state.rng)
        self._state = next_state
        frame = modes.active(next_state).view(next_state, events)
        return StepResult(frame=frame, events=events)

    def frame(self) -> SemanticFrame:
        """The current frame. Does not advance the turn."""
        return modes.active(self._state).view(self._state, ())

    def query(self, path: str) -> QueryResult:
        """The oracle: read world state by stable path. No turn advance.

        Unknown paths are error values, not exceptions. Stat queries carry
        their full derivation.
        """
        return _query(self._state, path)

    def fingerprint(self) -> RunFingerprint:
        """Engine version, pack id, seed, and turn."""
        return RunFingerprint.create(
            pack=self._pack_id, seed=self._seed, turn=self._state.turn
        )

    def snapshot(self) -> Snapshot:
        return Snapshot(_state=self._state, _seed=self._seed, _pack_id=self._pack_id)

    @classmethod
    def restore(cls, snap: Snapshot) -> Engine:
        return cls(state=snap._state, seed=snap._seed, pack_id=snap._pack_id)

    def _validate(self, command: Command) -> Rejected | None:
        """Answer validity against the frame's grammar, as the design requires.

        A rejection means the engine never ran the command: the turn does not
        advance and no events are emitted (0003 appendix A.4).
        """
        if self._state.flags.get(PLAYER_DEFEATED) and not isinstance(command, Look):
            # The one true reason: anything else would misdescribe the world.
            return Rejected(
                command=_render(command),
                reason="defeated",
                hint="you have fallen; only 'look' remains",
            )
        mode = modes.active(self._state)
        grammar = mode.available_commands(self._state)
        if command.verb not in mode.VERBS:
            # Not a thing you do in this mode — never "there are no exits":
            # a mode-absent verb must not misdescribe the world.
            return Rejected(
                command=_render(command),
                reason="wrong_mode",
                hint=(
                    f"not available during {mode.NAME}; "
                    f"try: {', '.join(grammar.verb_names())}"
                ),
            )
        vocabulary = _REJECTIONS.get(command.verb)
        if command.verb not in grammar.verb_names():
            if vocabulary is not None and command.args():
                # A real verb whose domain is empty right now: reject in its
                # own vocabulary, not as an unknown word.
                return Rejected(
                    command=_render(command),
                    reason=vocabulary.reason,
                    hint=vocabulary.empty_hint,
                )
            return Rejected(
                command=_render(command),
                reason="unknown_verb",
                hint=f"try one of: {', '.join(grammar.verb_names())}",
            )
        domains = grammar.domains(command.verb)
        for argument, domain in zip(command.args(), domains, strict=True):
            if argument not in domain:
                assert vocabulary is not None, "verbs with arguments have vocabulary"
                return Rejected(
                    command=_render(command),
                    reason=vocabulary.reason,
                    hint=vocabulary.hint(domain),
                )
        return None


@dataclass(frozen=True, slots=True)
class _RejectionVocabulary:
    reason: str
    options_hint: str
    empty_hint: str

    def hint(self, domain: tuple[str, ...]) -> str:
        if not domain:
            return self.empty_hint
        return f"{self.options_hint}: {', '.join(domain)}"


_REJECTIONS: dict[str, _RejectionVocabulary] = {
    "move": _RejectionVocabulary(
        "no_such_exit", "exits here", "there are no exits here"
    ),
    "take": _RejectionVocabulary(
        "not_here", "you can take", "there is nothing here to take"
    ),
    "use": _RejectionVocabulary(
        "not_usable", "you can use", "you are carrying nothing usable"
    ),
    "equip": _RejectionVocabulary(
        "not_equippable", "you can equip", "you are carrying nothing equippable"
    ),
    "attack": _RejectionVocabulary(
        "no_such_target", "you can attack", "there is nothing here to fight"
    ),
    "talk": _RejectionVocabulary(
        "no_one_to_talk_to", "you can talk to", "there is no one here to talk to"
    ),
    "open": _RejectionVocabulary(
        "nothing_to_open", "you can open", "there is nothing here to open"
    ),
    "choose": _RejectionVocabulary(
        "no_such_choice", "choose one of", "there is nothing to choose"
    ),
    "cast": _RejectionVocabulary(
        "cannot_cast", "you can cast", "you cannot cast anything"
    ),
}


def _render(command: Command) -> str:
    return " ".join((command.verb, *command.args()))
