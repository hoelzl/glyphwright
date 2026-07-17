"""The public surface is the whole contract an external harness sees."""

from __future__ import annotations

import pytest

from glyphwright import api
from glyphwright.api import Engine
from glyphwright.content.pack import reference_pack
from glyphwright.kernel.commands import Look, Move


def test_the_api_exports_everything_an_adapter_needs() -> None:
    # If an adapter must reach past this list, the surface is missing something.
    for name in ("Engine", "StepResult", "SemanticFrame", "Command", "Rejected"):
        assert hasattr(api, name)


def test_a_rejected_command_advances_nothing() -> None:
    engine = Engine.new(reference_pack(), seed=1)
    before = engine.frame()
    result = engine.step(Move("up"))
    assert not result.accepted
    assert result.rejection is not None
    assert result.rejection.reason == "no_such_exit"
    assert result.events == ()
    assert engine.frame().turn == before.turn


def test_a_rejection_carries_an_actionable_hint() -> None:
    engine = Engine.new(reference_pack(), seed=1)
    rejection = engine.step(Move("up")).rejection
    assert rejection is not None
    assert "east" in rejection.hint


def test_frame_does_not_advance_the_turn() -> None:
    engine = Engine.new(reference_pack(), seed=1)
    engine.step(Move("east"))
    assert engine.frame().turn == engine.frame().turn == 1


def test_the_frame_always_advertises_a_usable_grammar() -> None:
    engine = Engine.new(reference_pack(), seed=1)
    grammar = engine.frame().commands
    assert set(grammar.verb_names()) == {"move", "look", "wait"}
    assert grammar.domains("move")[0]


def test_look_is_accepted_and_costs_nothing() -> None:
    engine = Engine.new(reference_pack(), seed=1)
    result = engine.step(Look())
    assert result.accepted
    assert result.frame.turn == 0


def test_restore_is_independent_of_the_engine_it_came_from() -> None:
    engine = Engine.new(reference_pack(), seed=1)
    snapshot = engine.snapshot()
    engine.step(Move("east"))
    assert Engine.restore(snapshot).frame().turn == 0
    assert engine.frame().turn == 1


def test_a_new_run_is_reproducible_from_pack_and_seed() -> None:
    first = Engine.new(reference_pack(), seed=42).frame()
    second = Engine.new(reference_pack(), seed=42).frame()
    assert first == second


@pytest.mark.parametrize("seed", [0, 1, 424242, 2**63])
def test_any_seed_produces_a_usable_run(seed: int) -> None:
    assert Engine.new(reference_pack(), seed=seed).frame().turn == 0
