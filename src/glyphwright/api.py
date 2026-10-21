"""The only supported programmatic entry point.

Everything an external harness needs flows through this surface, versioned
independently of internals; nothing in ``kernel``, ``world``, ``modes``, or
``frames`` is public.

An adapter over this API is expected to be nearly mechanical. **If an adapter
needs logic, this surface is missing something**: that is a GlyphWright bug,
not an adapter concern.
"""

from __future__ import annotations

from dataclasses import dataclass

from glyphwright import modes
from glyphwright.content.pack import ContentPack
from glyphwright.content.reference import reference_pack
from glyphwright.frames.frame import SemanticFrame
from glyphwright.frontends.wire import (
    decode_command,
    encode_command,
    encode_event,
    encode_frame,
    encode_rejection,
)
from glyphwright.harness.fingerprint import RunFingerprint
from glyphwright.kernel.commands import (
    Command,
    CommandGrammar,
    Look,
    Move,
    Rejected,
    Wait,
)
from glyphwright.kernel.events import Event
from glyphwright.kernel.rng import Rng
from glyphwright.kernel.state import WorldState
from glyphwright.kernel.step import step as _step
from glyphwright.modes import exploration

__all__ = [
    "Command",
    "CommandGrammar",
    "ContentPack",
    "Engine",
    "Event",
    "Look",
    "Move",
    "Rejected",
    "RunFingerprint",
    "SemanticFrame",
    "Snapshot",
    "StepResult",
    "Wait",
    "decode_command",
    "encode_command",
    "encode_event",
    "encode_frame",
    "encode_rejection",
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
    """An opaque world state.

    Snapshots are free because state is immutable: the snapshot *is* the state.
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

    def fingerprint(self) -> RunFingerprint:
        """Engine version, pack id, seed, and turn."""
        return RunFingerprint.create(
            pack=self._pack_id, seed=self._seed, turn=self._state.turn
        )

    def snapshot(self) -> Snapshot:
        return Snapshot(_state=self._state, _seed=self._seed, _pack_id=self._pack_id)

    @classmethod
    def restore(cls, snap: Snapshot) -> Engine:
        """A plain engine at the snapshot's state."""
        return Engine(state=snap._state, seed=snap._seed, pack_id=snap._pack_id)

    def _validate(self, command: Command) -> Rejected | None:
        """Answer validity against the frame's grammar.

        A rejection means the engine never ran the command: the turn does not
        advance and no events are emitted.
        """
        mode = modes.active(self._state)
        grammar = mode.available_commands(self._state)
        # The grammar wins first: a verb the frame advertises is valid here
        # whatever the mode's static vocabulary says.
        if command.verb not in grammar.verb_names() and command.verb not in mode.VERBS:
            # Not a thing you do in this mode, which must never be described
            # as "there are no exits".
            return Rejected(
                command=encode_command(command),
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
                    command=encode_command(command),
                    reason=vocabulary.reason,
                    hint=vocabulary.empty_hint,
                )
            return Rejected(
                command=encode_command(command),
                reason="unknown_verb",
                hint=f"try one of: {', '.join(grammar.verb_names())}",
            )
        domains = grammar.domains(command.verb)
        for argument, domain in zip(command.args(), domains, strict=True):
            if argument not in domain:
                assert vocabulary is not None, "verbs with arguments have vocabulary"
                return Rejected(
                    command=encode_command(command),
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


# One entry per verb that takes arguments; later slices add theirs.
_REJECTIONS: dict[str, _RejectionVocabulary] = {
    "move": _RejectionVocabulary(
        "no_such_exit", "exits here", "there are no exits here"
    ),
}
