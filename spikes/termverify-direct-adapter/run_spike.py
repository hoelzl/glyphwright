"""Drive GlyphWright through TermVerify's DirectAdapter; emit a validated transcript.

What this proves, in order:

1. ``GlyphwrightApplication`` negotiates all seven constraints and reaches
   readiness under ``termverify.direct.DirectAdapter``.
2. A scripted session (accepted commands, a world-refusal, a typed rejection,
   an unparsable line, a resize, a clock advance, a stop) runs to a clean
   ``RunFinished``.
3. The session can be assembled into a ``termverify.transcript/v1`` that
   TermVerify's own strict codec accepts — the assembly code below is exactly
   the "recording harness" TermVerify does not ship yet (issue #114 ask 1).
4. Two identical runs produce byte-identical canonical transcripts.
5. A semantic key chord fails closed as ``adapter-runtime-failed`` /
   ``unsupported`` rather than being translated.

Run from the repository root (TermVerify is an overlay, never a project dep):

    uv --no-config run --with ../termverify \
        python spikes/termverify-direct-adapter/run_spike.py
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from glyphwright_application import GlyphwrightApplication
from termverify.adapter import (
    ClockAdvance,
    ClockConfiguration,
    Diagnostic,
    EnforcedConstraints,
    EpochCompleted,
    FilesystemConfiguration,
    KeyInput,
    ManualTime,
    NetworkConfiguration,
    Observation,
    Resize,
    RunConfiguration,
    RunFailed,
    RunFinished,
    Started,
    Stop,
    TerminalConfiguration,
    TerminalResult,
    TextInput,
)
from termverify.direct import DirectAdapter
from termverify.transcript import parse_transcript, serialize_transcript

from glyphwright import __version__ as GLYPHWRIGHT_VERSION
from glyphwright.api import reference_pack

RUN_ID = "run-glyphwright-direct-spike"
SEED = 424242
INITIAL_MS = 0

CONFIGURATION = RunConfiguration(
    seed=SEED,
    clock=ClockConfiguration(initial_ms=INITIAL_MS),
    locale="en-US",
    timezone="UTC",
    terminal=TerminalConfiguration(columns=80, rows=24, capabilities=()),
    filesystem=FilesystemConfiguration(root_id="glyphwright-spike"),
    network=NetworkConfiguration.deny(),
)

SUBJECT = {
    "format": "termverify.replay-subject/v1",
    "application": {
        "id": "glyphwright",
        "version": GLYPHWRIGHT_VERSION,
        "build": GLYPHWRIGHT_VERSION,
    },
    "fixture": {"id": "reference-vale", "version": "1"},
    "adapter": {"id": "glyphwright.direct-spike", "version": "1"},
    "normalizer": {"id": "glyphwright.plain", "version": "1"},
    "state_schema": {"id": "glyphwright.frame", "version": "5"},
}

SCRIPT = ("look", "move east", "move nowhere", "dance", "wait")


def thaw(value: Any) -> Any:
    """FrozenJsonValue back to plain JSON builtins for the transcript codec."""
    if isinstance(value, Mapping):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw(item) for item in value]
    if isinstance(value, bool) or value is None or isinstance(value, (str, float)):
        return value
    if isinstance(value, int):
        return int(value)  # ManualTime and friends back to exact int
    raise TypeError(f"not JSON: {type(value)!r}")


class TranscriptRecorder:
    """Assemble termverify.transcript/v1 records from direct-adapter results.

    This is the missing consumer-side piece written by hand: TermVerify
    defines the wire format and validates it, but ships nothing that turns
    adapter calls into transcript lines.
    """

    def __init__(self, run_id: str) -> None:
        self._run_id = run_id
        self._records: list[dict[str, Any]] = []

    def _emit(self, kind: str, payload: dict[str, Any]) -> None:
        sequence = len(self._records)
        self._records.append(
            {
                "protocol": "termverify.transcript/v1",
                "run_id": self._run_id,
                "seq": sequence,
                "id": f"record-{sequence:04d}",
                "kind": kind,
                "payload": payload,
            }
        )

    def started(self, configuration: RunConfiguration) -> None:
        self._emit(
            "run.started",
            {"config": thaw(configuration.to_protocol()), "subject": SUBJECT},
        )

    def capabilities(self, constraints: EnforcedConstraints) -> None:
        protocol = constraints.requested.to_protocol()
        for constraint in (
            "seed",
            "clock",
            "locale",
            "timezone",
            "terminal",
            "filesystem",
            "network",
        ):
            self._emit(
                "capability.result",
                {
                    "constraint": constraint,
                    "status": "enforced",
                    "effective": thaw(protocol[constraint]),
                },
            )

    def observation(self, observation: Observation) -> None:
        payload: dict[str, Any] = {
            "at_ms": int(observation.at_ms),
            "state": thaw(observation.state),
            "events": [
                {"type": event.type, "data": thaw(event.data)}
                for event in observation.events
            ],
            "ui": {
                "regions": [
                    {
                        "id": region.id,
                        "role": region.role,
                        "bounds": {
                            "column": region.column,
                            "row": region.row,
                            "columns": region.columns,
                            "rows": region.rows,
                        },
                    }
                    for region in observation.ui.regions
                ],
                "focus": observation.ui.focus,
                "cursor": {
                    "column": observation.ui.cursor.column,
                    "row": observation.ui.cursor.row,
                    "visible": observation.ui.cursor.visible,
                },
                "mode": observation.ui.mode,
            },
        }
        if observation.frame is not None:
            payload["frame"] = {
                "lines": list(observation.frame.lines),
                "columns": observation.frame.columns,
                "rows": observation.frame.rows,
            }
        if observation.process is not None:
            process: dict[str, Any] = {"state": observation.process.state}
            if observation.process.exit is not None:
                process["exit"] = {
                    "kind": observation.process.exit.kind,
                    "value": observation.process.exit.value,
                }
            payload["process"] = process
        self._emit("observation", payload)

    def diagnostics(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        for diagnostic in diagnostics:
            payload: dict[str, Any] = {
                "at_ms": int(diagnostic.at_ms),
                "code": diagnostic.code,
                "message": diagnostic.message,
            }
            if diagnostic.details is not None:
                payload["details"] = thaw(diagnostic.details)
            self._emit("diagnostic", payload)

    def epoch(self, kind: str, payload: dict[str, Any], result: EpochCompleted) -> None:
        self._emit(kind, payload)
        self.diagnostics(result.diagnostics)
        self.observation(result.observation)

    def finished(self, result: TerminalResult, at_ms: int) -> None:
        assert isinstance(result.outcome, RunFinished)
        self._emit("input.stop", {"at_ms": at_ms})
        self.diagnostics(result.diagnostics)
        if result.observation is not None:
            self.observation(result.observation)
        self._emit(
            "run.finished",
            {
                "exit": {
                    "kind": result.outcome.exit.kind,
                    "value": result.outcome.exit.value,
                }
            },
        )

    def serialize(self) -> bytes:
        return serialize_transcript(self._records)


def run_scripted_session() -> bytes:
    """One full session; returns the canonical transcript bytes."""
    application = GlyphwrightApplication(reference_pack())
    adapter = DirectAdapter(application)
    recorder = TranscriptRecorder(RUN_ID)

    recorder.started(CONFIGURATION)
    start = adapter.start(RUN_ID, CONFIGURATION)
    assert isinstance(start, Started), f"start did not reach readiness: {start!r}"
    recorder.capabilities(start.constraints)
    recorder.observation(start.observation)

    time = ManualTime(INITIAL_MS)
    for text in SCRIPT:
        result = adapter.dispatch(TextInput(at_ms=time, text=text))
        assert isinstance(result, EpochCompleted), f"{text!r} ended the run: {result!r}"
        recorder.epoch("input.text", {"at_ms": int(time), "text": text}, result)

    result = adapter.dispatch(Resize(at_ms=time, columns=120, rows=40))
    assert isinstance(result, EpochCompleted)
    recorder.epoch(
        "input.resize", {"at_ms": int(time), "columns": 120, "rows": 40}, result
    )

    advanced = ManualTime(int(time) + 1000)
    result = adapter.advance_clock(ClockAdvance(at_ms=advanced, delta_ms=1000))
    assert isinstance(result, EpochCompleted)
    recorder.epoch(
        "input.clock_advanced", {"at_ms": int(advanced), "delta_ms": 1000}, result
    )
    time = advanced

    terminal = adapter.stop(Stop(at_ms=time))
    assert isinstance(terminal.outcome, RunFinished), f"stop failed: {terminal!r}"
    assert terminal.outcome.exit.value == 0
    recorder.finished(terminal, int(time))
    return recorder.serialize()


def run_key_refusal() -> None:
    """A semantic chord must fail closed, never be translated to text."""
    application = GlyphwrightApplication(reference_pack())
    adapter = DirectAdapter(application)
    start = adapter.start(RUN_ID, CONFIGURATION)
    assert isinstance(start, Started)
    result = adapter.dispatch(
        KeyInput(at_ms=ManualTime(INITIAL_MS), keys=("Control", "c"))
    )
    assert isinstance(result, TerminalResult), result
    assert isinstance(result.outcome, RunFailed), result.outcome
    details = result.outcome.failure.details
    assert isinstance(details, Mapping) and details["input_kind"] == "key", details


def main() -> int:
    first = run_scripted_session()
    second = run_scripted_session()
    assert first == second, "identical runs must serialize to identical bytes"

    records = parse_transcript(first)
    kinds = [record["kind"] for record in records]
    assert kinds[0] == "run.started" and kinds[-1] == "run.finished"
    assert kinds.count("capability.result") == 7
    diagnostic_codes = [
        record["payload"]["code"]
        for record in records
        if record["kind"] == "diagnostic"
    ]
    assert diagnostic_codes == ["command-rejected", "command-unparsable"], (
        diagnostic_codes
    )

    run_key_refusal()

    out = Path(__file__).resolve().parent / "transcript.jsonl"
    out.write_bytes(first)
    print(f"OK: {len(records)} records, deterministic, validated -> {out.name}")
    counts = {kind: kinds.count(kind) for kind in sorted(set(kinds))}
    print(f"    kinds: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
