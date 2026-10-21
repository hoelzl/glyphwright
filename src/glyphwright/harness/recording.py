"""Session recording and replay: the durable run format.

A run is the rules revision, the pack id, the seed, and the commands;
everything else is derivable, so everything else is verification. A recording
is JSON lines: the session header, then one line per accepted step with the
command and a SHA-256 digest of the step's encoded events. Replay re-runs the
commands and compares the digests: it does not trust determinism, it checks
it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import IO

from glyphwright.api import Engine, StepResult
from glyphwright.content.pack import ContentPack
from glyphwright.frontends.wire import (
    canonical_json,
    decode_command,
    encode_command,
    encode_event,
)
from glyphwright.harness.fingerprint import RULES, header_problem
from glyphwright.kernel.commands import Command
from glyphwright.kernel.events import Event
from glyphwright.kernel.state import WorldState

RECORDING_SCHEMA = "glyphwright.recording/1"
_BOM = "﻿"


def events_digest(events: tuple[Event, ...], *, turn: int) -> str:
    """SHA-256 over one step's canonically encoded events."""
    canonical = canonical_json([encode_event(event, turn=turn) for event in events])
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def step_line(command: Command, result: StepResult, *, step: int) -> dict[str, object]:
    """One recorded step: the command as text, and its events' digest."""
    return {
        "schema": RECORDING_SCHEMA,
        "step": step,
        "command": encode_command(command),
        "events": events_digest(result.events, turn=result.frame.turn),
    }


class RecordingEngine(Engine):
    """An engine that appends its run to a sink as it goes.

    The header is written at construction, and each accepted step appends a
    line. Rejections and queries change nothing, so they are not part of the
    run and are not recorded. Frontends need no change: this is an
    :class:`Engine`.
    """

    def __init__(
        self, state: WorldState, seed: int, pack_id: str, sink: IO[str]
    ) -> None:
        super().__init__(state=state, seed=seed, pack_id=pack_id)
        self._sink = sink
        self._steps = 0

    @classmethod
    def recording(
        cls, pack: ContentPack, *, seed: int, sink: IO[str], harness: bool = False
    ) -> RecordingEngine:
        # Adopt what Engine.new derived, so recordings cannot drift from it.
        base = Engine.new(pack, seed=seed)
        engine = cls(state=base._state, seed=seed, pack_id=base._pack_id, sink=sink)
        engine._write(engine.fingerprint().header(harness=harness))
        return engine

    def step(self, command: Command) -> StepResult:
        result = super().step(command)
        if result.accepted:
            self._steps += 1
            self._write(step_line(command, result, step=self._steps))
        return result

    def _write(self, payload: dict[str, object]) -> None:
        self._sink.write(canonical_json(payload) + "\n")
        self._sink.flush()


@dataclass(frozen=True, slots=True)
class Replay:
    """What replaying a recording established.

    A divergence is data, not an exception: ``problem`` names the step and the
    mismatch. ``engine`` is the rebuilt run, set only when every step
    verified.
    """

    ok: bool
    steps: int
    problem: str | None = None
    engine: Engine | None = None


def _fail(steps: int, problem: str) -> Replay:
    return Replay(ok=False, steps=steps, problem=problem)


def _lines(source: Iterable[str]) -> Iterator[str]:
    for number, line in enumerate(source):
        # v0 finding H8: an editor's byte-order mark broke the header.
        if number == 0:
            line = line.removeprefix(_BOM)
        if line.strip():
            yield line


def replay(pack: ContentPack, source: Iterable[str]) -> Replay:
    """Re-run a recording against ``pack`` and check every step.

    The header is the compatibility contract: another rules revision or
    another pack is refused by name instead of replaying subtly wrong. The
    release version is not compared, because a release need not change
    behaviour (decision 0003). The returned engine stands at the recording's
    final state, RNG cursor included.
    """
    lines = _lines(source)
    try:
        raw = next(lines)
    except StopIteration:
        return _fail(0, "the recording is empty: no session header")
    try:
        header = json.loads(raw)
    except json.JSONDecodeError:
        return _fail(0, "the session header is not JSON")
    problem = header_problem(header)
    if problem is not None:
        return _fail(0, problem)
    if header["rules"] != RULES:
        return _fail(
            0,
            f"recorded under rules {header['rules']}, replaying under rules "
            f"{RULES}: the engine's behaviour changed since; re-record",
        )
    if header["pack"] != pack.pack_id:
        return _fail(
            0,
            f"recorded against pack {header['pack']!r}, "
            f"replaying against {pack.pack_id!r}",
        )

    engine = Engine.new(pack, seed=header["seed"])
    steps = 0
    for raw in lines:
        expected = steps + 1
        where = f"step {expected}"
        try:
            line = json.loads(raw)
        except json.JSONDecodeError:
            return _fail(steps, f"{where}: the line is not JSON")
        if not isinstance(line, dict) or line.get("schema") != RECORDING_SCHEMA:
            return _fail(steps, f"{where}: not a {RECORDING_SCHEMA} line")
        numbered = line.get("step")
        if numbered != expected or isinstance(numbered, bool):
            return _fail(steps, f"{where}: the line is numbered {numbered!r}")
        text = line.get("command")
        command = decode_command(text) if isinstance(text, str) else None
        if command is None:
            return _fail(steps, f"{where}: {text!r} is not a command")
        result = engine.step(command)
        if result.rejection is not None:
            return _fail(
                steps,
                f"{where}: {text!r} was rejected ({result.rejection.reason}), "
                "but the recorded run accepted it",
            )
        digest = events_digest(result.events, turn=result.frame.turn)
        if digest != line.get("events"):
            return _fail(
                steps,
                f"{where}: {text!r} produced different events than recorded",
            )
        steps = expected
    return Replay(ok=True, steps=steps, engine=engine)
