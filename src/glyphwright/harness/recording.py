"""Session recording and replay: the durable run format (design 0008).

A run is (engine version, pack hash, seed, commands) — everything else is
derivable, so everything else is verification. A recording is JSON lines: the
session header, then one line per accepted step carrying the command in the
command language and a SHA-256 digest of the step's encoded events. Replay
re-executes the commands and compares digests: it does not trust determinism,
it verifies it (0003 §20.2, resolved).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import IO

from glyphwright import __version__
from glyphwright.api import Engine, StepResult
from glyphwright.content.pack import ContentPack
from glyphwright.frontends.wire import decode_command, encode_command, encode_event
from glyphwright.harness.fingerprint import SESSION_SCHEMA
from glyphwright.kernel.commands import Command
from glyphwright.kernel.events import Event

RECORDING_SCHEMA = "glyphwright.recording/1"


def events_digest(events: tuple[Event, ...], *, turn: int) -> str:
    """The per-step prefix hash: SHA-256 over the canonically encoded events."""
    canonical = json.dumps(
        [encode_event(event, turn=turn) for event in events],
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def step_line(command: Command, result: StepResult, *, step: int) -> dict[str, object]:
    """One recorded step: the command language text plus the events digest."""
    return {
        "schema": RECORDING_SCHEMA,
        "step": step,
        "command": encode_command(command),
        "events": events_digest(result.events, turn=result.frame.turn),
    }


class RecordingEngine(Engine):
    """An engine that appends its run to a sink as it goes.

    The header is written at construction; each accepted step appends one
    line. Rejections and queries advance nothing, so they are not part of
    the run's identity and are not recorded (design 0008 §1). Frontends
    need no changes: this *is* an :class:`Engine`.
    """

    _sink: IO[str]
    _steps: int

    @classmethod
    def recording(
        cls, pack: ContentPack, *, seed: int, sink: IO[str], harness: bool = False
    ) -> RecordingEngine:
        base = Engine.new(pack, seed=seed)
        engine = cls(state=base._state, seed=seed, pack_id=pack.pack_id)
        engine._sink = sink
        engine._steps = 0
        engine._write(engine.fingerprint().header(harness=harness))
        return engine

    def step(self, command: Command) -> StepResult:
        result = super().step(command)
        if result.accepted:
            self._steps += 1
            self._write(step_line(command, result, step=self._steps))
        return result

    def _write(self, payload: dict[str, object]) -> None:
        self._sink.write(json.dumps(payload, sort_keys=True) + "\n")
        self._sink.flush()


@dataclass(frozen=True, slots=True)
class Replay:
    """What replaying a recording established.

    A divergence is data, not an exception: ``problem`` names the step and
    the mismatch, ``engine`` is the rebuilt run when — and only when — every
    step verified.
    """

    ok: bool
    steps: int
    problem: str | None = None
    engine: Engine | None = None


def _fail(steps: int, problem: str) -> Replay:
    return Replay(ok=False, steps=steps, problem=problem)


def _lines(source: Iterable[str]) -> Iterator[str]:
    return (line for line in source if line.strip())


def replay(pack: ContentPack, source: Iterable[str]) -> Replay:
    """Re-execute a recording against ``pack`` and verify every step.

    The header is the compatibility contract: an engine-version or pack
    mismatch refuses loudly instead of replaying subtly wrong — the
    fingerprint doing its job (0003 §14). The returned engine stands at the
    recording's final state; fold-equivalence guarantees it byte-exactly,
    RNG cursor included.
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
    if not isinstance(header, dict) or header.get("schema") != SESSION_SCHEMA:
        return _fail(0, f"the first line is not a {SESSION_SCHEMA} header")
    expected_engine = f"glyphwright {__version__}"
    if header.get("engine") != expected_engine:
        return _fail(
            0,
            f"recorded by {header.get('engine')!r}, replaying with "
            f"{expected_engine!r}: recordings do not migrate across versions",
        )
    if header.get("pack") != pack.pack_id:
        return _fail(
            0,
            f"recorded against pack {header.get('pack')!r}, "
            f"replaying against {pack.pack_id!r}",
        )
    seed = header.get("seed")
    if not isinstance(seed, int):
        return _fail(0, f"the header's seed is not an integer: {seed!r}")

    engine = Engine.new(pack, seed=seed)
    steps = 0
    for raw in lines:
        expected_step = steps + 1
        where = f"step {expected_step}"
        try:
            line = json.loads(raw)
        except json.JSONDecodeError:
            return _fail(steps, f"{where}: the line is not JSON")
        if not isinstance(line, dict) or line.get("schema") != RECORDING_SCHEMA:
            return _fail(steps, f"{where}: not a {RECORDING_SCHEMA} line")
        if line.get("step") != expected_step:
            return _fail(steps, f"{where}: the line is numbered {line.get('step')!r}")
        text = line.get("command")
        command = decode_command(text) if isinstance(text, str) else None
        if command is None:
            return _fail(steps, f"{where}: {text!r} is not command language")
        result = engine.step(command)
        if not result.accepted:
            assert result.rejection is not None
            return _fail(
                steps,
                f"{where}: {text!r} was rejected ({result.rejection.reason}) — "
                "the recorded run accepted it",
            )
        digest = events_digest(result.events, turn=result.frame.turn)
        if digest != line.get("events"):
            return _fail(
                steps,
                f"{where}: events diverged — recorded {line.get('events')!r}, "
                f"replayed {digest!r}",
            )
        steps = expected_step
    return Replay(ok=True, steps=steps, engine=engine)
