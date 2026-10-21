"""The only supported programmatic entry point.

Everything an external harness needs flows through this surface, versioned
independently of internals; nothing in ``kernel``, ``world``, ``modes``, or
``frames`` is public.

An adapter over this API is expected to be nearly mechanical. **If an adapter
needs logic, this surface is missing something**: that is a GlyphWright bug,
not an adapter concern.
"""

from __future__ import annotations

import functools
import os
from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

from glyphwright import modes
from glyphwright.content.loader import PackError, parse_pack
from glyphwright.content.pack import ContentPack
from glyphwright.frames.frame import SemanticFrame
from glyphwright.frontends.wire import (
    VERB_SPECS,
    decode_command,
    encode_command,
    encode_event,
    encode_frame,
    encode_rejection,
)
from glyphwright.harness.fingerprint import RunFingerprint
from glyphwright.harness.query import QueryResult
from glyphwright.harness.query import query as _query
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
    "PackError",
    "QueryResult",
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
    "load_pack",
    "reference_pack",
]


def load_pack(root: Traversable | str | os.PathLike[str]) -> ContentPack:
    """Load a content pack from a directory of TOML files.

    The core does no I/O, so reading happens here and the loader parses text.
    Raises :class:`PackError`, located to file and line, for every problem.
    """
    directory: Traversable = (
        root if isinstance(root, Traversable) else Path(os.fspath(root))
    )
    if not directory.is_dir():
        raise PackError(None, None, None, f"{root} is not a pack directory")
    sources: dict[str, str] = {}
    for child in directory.iterdir():
        if not child.is_file() or not child.name.endswith(".toml"):
            continue
        try:
            sources[child.name] = child.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise PackError(
                child.name, None, None, f"not valid UTF-8 ({error})"
            ) from error
        except OSError as error:
            raise PackError(child.name, None, None, f"cannot read ({error})") from error
    return parse_pack(sources)


@functools.cache
def reference_pack() -> ContentPack:
    """The built-in reference pack, loaded like any external pack."""
    return load_pack(files("glyphwright.content") / "packs" / "reference-vale")


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

    def query(self, path: str) -> QueryResult:
        """Read world state by a stable path. The turn does not pass.

        An unknown path is an error value, not an exception. Stat queries
        carry their full derivation.
        """
        return _query(self._state, path)

    def fingerprint(self) -> RunFingerprint:
        """Engine version, rules revision, pack id, seed, and turn."""
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
        if self._state.defeated and not isinstance(command, Look):
            # The one true reason: anything else would misdescribe the world.
            return Rejected(
                command=encode_command(command),
                reason="defeated",
                hint="you are defeated; only 'look' remains",
            )
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
        spec = VERB_SPECS.get(command.verb)
        if command.verb not in grammar.verb_names():
            if spec is not None and spec.reason is not None and command.args():
                # A real verb whose domain is empty right now: reject in its
                # own vocabulary, not as an unknown word.
                return Rejected(
                    command=encode_command(command),
                    reason=spec.reason,
                    hint=spec.empty_hint or "",
                )
            return Rejected(
                command=encode_command(command),
                reason="unknown_verb",
                hint=f"try one of: {', '.join(grammar.verb_names())}",
            )
        domains = grammar.domains(command.verb)
        for argument, domain in zip(command.args(), domains, strict=True):
            if argument not in domain:
                assert spec is not None and spec.reason is not None, (
                    "verbs with arguments have a rejection reason"
                )
                hint = (
                    f"{spec.options_hint}: {', '.join(domain)}"
                    if domain
                    else spec.empty_hint or ""
                )
                return Rejected(
                    command=encode_command(command), reason=spec.reason, hint=hint
                )
        return None
