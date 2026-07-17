"""Kernel semantics: purity, fold equivalence, and movement rules."""

from __future__ import annotations

import dataclasses

import pytest

from glyphwright.api import Engine
from glyphwright.content.pack import reference_pack
from glyphwright.kernel.commands import Look, Move, Wait
from glyphwright.kernel.events import MoveBlocked, Moved, TurnAdvanced
from glyphwright.kernel.state import PLAYER, WorldState, fold
from glyphwright.kernel.step import step


@pytest.fixture
def state() -> WorldState:
    return Engine.new(reference_pack(), seed=1)._state


def _at(state: WorldState) -> str:
    at = state.entity(PLAYER).at()
    assert at is not None
    return str(at)


def test_the_player_starts_where_the_pack_says(state: WorldState) -> None:
    assert _at(state) == "village:1,1"


def test_moving_emits_moved_then_turn_advanced(state: WorldState) -> None:
    nxt, events = step(state, Move("east"), state.rng)
    assert [type(event) for event in events] == [Moved, TurnAdvanced]
    assert _at(nxt) == "village:2,1"
    assert nxt.turn == state.turn + 1


def test_a_wall_refuses_the_move_without_moving_the_player(state: WorldState) -> None:
    nxt, events = step(state, Move("north"), state.rng)
    assert isinstance(events[0], MoveBlocked)
    assert events[0].reason == "wall"
    assert _at(nxt) == _at(state), "a blocked move must not relocate the actor"


def test_a_blocked_move_still_spends_the_turn(state: WorldState) -> None:
    nxt, _ = step(state, Move("north"), state.rng)
    assert nxt.turn == state.turn + 1


def test_waiting_spends_a_turn_and_emits_only_that(state: WorldState) -> None:
    nxt, events = step(state, Wait(), state.rng)
    assert [type(event) for event in events] == [TurnAdvanced]
    assert nxt.turn == state.turn + 1
    assert _at(nxt) == _at(state)


def test_looking_is_an_observation_not_a_turn(state: WorldState) -> None:
    nxt, events = step(state, Look(), state.rng)
    assert events == ()
    assert nxt.turn == state.turn


def test_step_does_not_mutate_its_input(state: WorldState) -> None:
    before = dataclasses.replace(state)
    before_position = _at(state)
    step(state, Move("east"), state.rng)
    assert _at(state) == before_position
    assert state.turn == before.turn


def test_state_is_deeply_immutable(state: WorldState) -> None:
    with pytest.raises(TypeError):
        state.entities["player"] = None  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.turn = 99  # type: ignore[misc]


def test_successor_state_is_the_fold_of_its_events(state: WorldState) -> None:
    nxt, events = step(state, Move("east"), state.rng)
    folded = fold(state, events)
    assert _at(folded) == _at(nxt)
    assert folded.turn == nxt.turn


def test_the_mode_stack_never_empties(state: WorldState) -> None:
    assert state.mode == "exploration"
    with pytest.raises(ValueError):
        dataclasses.replace(state, mode_stack=())
