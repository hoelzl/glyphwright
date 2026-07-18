"""GlyphWright as a TermVerify ``DirectApplication`` (spike).

Maps ``glyphwright.api`` onto TermVerify's direct in-process producer contract
(`termverify.adapter` + `termverify.direct`). Design 0003 §14 predicts this
mapping is nearly mechanical; every place it is not is a finding, recorded in
this spike's README.

Contract obligations honoured here (termverify docs/developer-guide/direct-adapter.md):

- Receipts echo the requested values exactly (the binding check requires it);
  a constraint GlyphWright cannot honour is a structured ``ConstraintUnsupported``.
- Observations and diagnostics use the active epoch's manual time.
- A semantic key chord is *not* translated to text: GlyphWright's kernel speaks
  commands, keys exist only in the TUI (0003 ADR-003), so ``KeyInput`` is a
  deterministic ``adapter-runtime-failed`` with ``reason: unsupported``.
- Quiescence is trivial: the engine is synchronous, every ``step`` returns at
  quiescence by construction.
"""

from __future__ import annotations

from termverify.adapter import (
    AdapterFailure,
    ClockAdvance,
    ClockConfiguration,
    ClockReceipt,
    ConstraintUnsupported,
    Cursor,
    Diagnostic,
    DispatchInput,
    EpochCompleted,
    Event,
    ExitStatus,
    FilesystemConfiguration,
    FilesystemReceipt,
    Frame,
    KeyInput,
    LocaleReceipt,
    ManualTime,
    NetworkConfiguration,
    NetworkReceipt,
    Observation,
    ProcessObservation,
    Resize,
    RunFinished,
    SeedReceipt,
    Stop,
    TerminalConfiguration,
    TerminalReceipt,
    TerminalResult,
    TextInput,
    TimezoneReceipt,
    UiObservation,
)

from glyphwright.api import (
    ContentPack,
    Engine,
    decode_command,
    encode_event,
    encode_frame,
    encode_rejection,
)

# The one deliberate reach past glyphwright.api: the plain renderer is this
# adapter's *normalizer* (subject selector "glyphwright.plain"), an optional
# evidence layer, not a semantic need. Frontends are shipped interaction
# surfaces, not internals (0003 §12).
from glyphwright.frontends import plain


class GlyphwrightApplication:
    """One GlyphWright run behind TermVerify's constraint and execution ports."""

    def __init__(self, pack: ContentPack) -> None:
        self._pack = pack
        self._engine: Engine | None = None
        self._seed: int | None = None
        self._initial_ms: int | None = None

    # -- ConstraintPorts ---------------------------------------------------
    # The kernel is deterministic by construction: the seed is an Engine.new
    # argument, time is the turn counter, and there is no locale-, timezone-,
    # filesystem-, or network-dependent behaviour anywhere in the engine
    # (AGENTS.md invariants). Enforcement is therefore either a real injection
    # (seed) or a vacuous truth we can honestly receipt.

    def enforce_seed(
        self, run_id: str, requested: int
    ) -> SeedReceipt | ConstraintUnsupported | AdapterFailure:
        self._seed = requested
        return SeedReceipt(run_id=run_id, effective=requested)

    def enforce_clock(
        self, run_id: str, requested: ClockConfiguration
    ) -> ClockReceipt | ConstraintUnsupported | AdapterFailure:
        # GlyphWright has no wall clock; manual time is bookkeeping the
        # harness owns and the world never reads.
        self._initial_ms = requested.initial_ms
        return ClockReceipt(run_id=run_id, effective=requested)

    def enforce_locale(
        self, run_id: str, requested: str
    ) -> LocaleReceipt | ConstraintUnsupported | AdapterFailure:
        # ASCII-first rendering (0003 ADR-007); output is locale-invariant.
        return LocaleReceipt(run_id=run_id, effective=requested)

    def enforce_timezone(
        self, run_id: str, requested: str
    ) -> TimezoneReceipt | ConstraintUnsupported | AdapterFailure:
        if requested != "UTC":
            return ConstraintUnsupported(
                "timezone",
                "constraint-unsupported",
                "glyphwright has no clock; only UTC is meaningful",
            )
        return TimezoneReceipt(run_id=run_id, effective=requested)

    def enforce_terminal(
        self, run_id: str, requested: TerminalConfiguration
    ) -> TerminalReceipt | ConstraintUnsupported | AdapterFailure:
        if requested.capabilities:
            return ConstraintUnsupported(
                "terminal",
                "constraint-unsupported",
                "terminal capabilities are not enforceable in-process",
            )
        # Dimensions are advisory: semantic frames are size-independent and
        # the plain rendering wraps nothing.
        return TerminalReceipt(run_id=run_id, effective=requested)

    def enforce_filesystem(
        self, run_id: str, requested: FilesystemConfiguration
    ) -> FilesystemReceipt | ConstraintUnsupported | AdapterFailure:
        # The engine performs no filesystem I/O; the sandbox is vacuously honoured.
        return FilesystemReceipt(run_id=run_id, effective=requested)

    def enforce_network(
        self, run_id: str, requested: NetworkConfiguration
    ) -> NetworkReceipt | ConstraintUnsupported | AdapterFailure:
        if requested.mode != "deny":
            return ConstraintUnsupported(
                "network",
                "constraint-unsupported",
                "glyphwright never touches the network; only deny is meaningful",
            )
        return NetworkReceipt(run_id=run_id, effective=requested)

    # -- DirectApplication ---------------------------------------------------

    def initialize(self) -> EpochCompleted | TerminalResult | AdapterFailure:
        assert self._seed is not None and self._initial_ms is not None
        self._engine = Engine.new(self._pack, self._seed)
        return EpochCompleted(self._observe(ManualTime(self._initial_ms)))

    def dispatch(
        self, input_event: DispatchInput
    ) -> EpochCompleted | TerminalResult | AdapterFailure:
        at_ms = input_event.at_ms
        if isinstance(input_event, KeyInput):
            # Keys exist only in the TUI (0003 ADR-003). Refusing here, not
            # translating, is what the direct-adapter contract demands.
            return AdapterFailure(
                "adapter-runtime-failed",
                "glyphwright's kernel speaks semantic commands; "
                "drive it with TextInput",
                {"input_kind": "key", "reason": "unsupported"},
            )
        if isinstance(input_event, Resize):
            # Presentation-only: semantic frames are size-independent.
            return EpochCompleted(self._observe(at_ms))
        return self._dispatch_text(input_event, at_ms)

    def _dispatch_text(
        self, input_event: TextInput, at_ms: ManualTime
    ) -> EpochCompleted:
        engine = self._require_engine()
        command = decode_command(input_event.text)
        if command is None:
            diagnostic = Diagnostic(
                at_ms,
                "command-unparsable",
                f"not a glyphwright command: {input_event.text!r}",
            )
            return EpochCompleted(self._observe(at_ms), (diagnostic,))
        result = engine.step(command)
        if result.rejection is not None:
            # A rejection is data, not a failure: the engine never ran the
            # command and the turn did not advance (0003 appendix A.4).
            diagnostic = Diagnostic(
                at_ms,
                "command-rejected",
                result.rejection.reason,
                encode_rejection(result.rejection, turn=result.frame.turn),
            )
            return EpochCompleted(self._observe(at_ms), (diagnostic,))
        events = tuple(
            Event(payload["type"], payload)
            for payload in (
                encode_event(event, turn=result.frame.turn) for event in result.events
            )
        )
        return EpochCompleted(self._observe(at_ms, events))

    def advance_clock(
        self, input_event: ClockAdvance
    ) -> EpochCompleted | TerminalResult | AdapterFailure:
        # Time is the turn counter; wall time passing changes nothing.
        return EpochCompleted(self._observe(input_event.at_ms))

    def stop(self, input_event: Stop) -> TerminalResult | AdapterFailure:
        exit_status = ExitStatus("code", 0)
        observation = self._observe(
            input_event.at_ms, process=ProcessObservation.exited(exit_status)
        )
        return TerminalResult(observation, RunFinished(exit_status))

    def abort(self, input_event: Stop) -> None:
        # Nothing to clean up: no subprocess, no files, no sockets.
        return None

    # -- Observation mapping ---------------------------------------------------

    def _require_engine(self) -> Engine:
        assert self._engine is not None, "initialize() has not run"
        return self._engine

    def _observe(
        self,
        at_ms: ManualTime,
        events: tuple[Event, ...] = (),
        process: ProcessObservation | None = None,
    ) -> Observation:
        engine = self._require_engine()
        frame = engine.frame()
        state = encode_frame(frame)
        rendered = plain.render(frame).splitlines()
        return Observation(
            at_ms=at_ms,
            state=state,
            events=events,
            ui=UiObservation(
                regions=(),
                focus=None,
                cursor=Cursor(column=0, row=0, visible=False),
                mode=str(state["mode"]),
            ),
            frame=Frame(
                lines=tuple(rendered),
                columns=max(1, max(len(line) for line in rendered)),
                rows=len(rendered),
            ),
            process=process if process is not None else ProcessObservation.running(),
        )
