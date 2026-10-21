"""The step function: purity, fold equivalence, and the exploration rules."""

from __future__ import annotations

import pytest

from glyphwright.frames.frame import GridView
from glyphwright.kernel.commands import Look, Move, Wait
from glyphwright.kernel.events import MoveBlocked, Moved, TurnAdvanced
from glyphwright.kernel.rng import Rng
from glyphwright.kernel.state import MODE_EXPLORATION, PLAYER, WorldState, fold
from glyphwright.kernel.step import step
from glyphwright.modes import exploration
from glyphwright.world.entities import Actor, Blocker, Entity, Position, Renderable
from glyphwright.world.grid import GridSpace

ROOM = GridSpace.from_text("room", "#####\n#...#\n#...#\n#####")


def _actor(entity_id: str, x: int, y: int, *, blocks: bool = False) -> Entity:
    return Entity(
        id=entity_id,
        position=Position(at=ROOM.pos(x, y)),
        actor=Actor(name=entity_id.title(), hp=5, max_hp=5),
        blocker=Blocker() if blocks else None,
        renderable=Renderable(glyph=entity_id[0], label=entity_id),
    )


@pytest.fixture
def state() -> WorldState:
    return WorldState(
        entities={
            PLAYER: _actor(PLAYER, 1, 1),
            "rock": _actor("rock", 3, 1, blocks=True),
        },
        areas={"room": ROOM},
        mode_stack=(MODE_EXPLORATION,),
        turn=0,
        rng=Rng.from_seed(1),
    )


def _at(state: WorldState) -> str:
    return str(state.entity(PLAYER).at())


def test_moving_emits_moved_then_turn_advanced(state: WorldState) -> None:
    nxt, events = step(state, Move("east"), state.rng)
    assert [type(event) for event in events] == [Moved, TurnAdvanced]
    assert _at(nxt) == "room:2,1"
    assert nxt.turn == state.turn + 1


def test_a_wall_refuses_the_move_and_still_spends_the_turn(state: WorldState) -> None:
    nxt, events = step(state, Move("north"), state.rng)
    assert isinstance(events[0], MoveBlocked)
    assert events[0].reason == "wall"
    assert _at(nxt) == _at(state)
    assert nxt.turn == state.turn + 1


def test_an_occupied_tile_refuses_the_move(state: WorldState) -> None:
    moved, _ = step(state, Move("east"), state.rng)
    nxt, events = step(moved, Move("east"), moved.rng)
    assert isinstance(events[0], MoveBlocked)
    assert events[0].reason == "occupied"
    assert _at(nxt) == "room:2,1"


def test_waiting_spends_a_turn_and_emits_only_that(state: WorldState) -> None:
    nxt, events = step(state, Wait(), state.rng)
    assert [type(event) for event in events] == [TurnAdvanced]
    assert nxt.turn == state.turn + 1
    assert _at(nxt) == _at(state)


def test_looking_is_an_observation_not_a_turn(state: WorldState) -> None:
    nxt, events = step(state, Look(), state.rng)
    assert events == ()
    assert nxt == state


def test_step_accepts_a_cursor_other_than_the_states(state: WorldState) -> None:
    # Finding K1: v0 raised here, because it compared the handler's cursor
    # with the state's instead of the one it was given.
    other = Rng.from_seed(999)
    nxt, events = step(state, Look(), other)
    assert events == ()
    assert nxt == state


def test_the_closing_event_carries_the_cursor_it_was_given(state: WorldState) -> None:
    other = Rng.from_seed(999)
    nxt, events = step(state, Wait(), other)
    assert events[-1] == TurnAdvanced(turn=1, rng=other.encode())
    assert nxt.rng == other


def test_successor_state_is_exactly_the_fold_of_its_events(state: WorldState) -> None:
    for command in (Move("east"), Move("north"), Wait(), Look()):
        nxt, events = step(state, command, state.rng)
        assert fold(state, events) == nxt


def test_step_does_not_mutate_its_input(state: WorldState) -> None:
    before = (_at(state), state.turn, state.rng)
    step(state, Move("east"), state.rng)
    assert (_at(state), state.turn, state.rng) == before


def test_the_grammar_offers_every_exit_including_walls(state: WorldState) -> None:
    grammar = exploration.available_commands(state)
    assert grammar.verb_names() == ("move", "look", "wait")
    assert grammar.domains("move") == (("east", "north", "south", "west"),)


def test_move_is_not_advertised_where_there_are_no_exits() -> None:
    void = GridSpace.from_text("void", ".")
    lone = Entity(
        id=PLAYER,
        position=Position(at=void.pos(0, 0)),
        actor=Actor(name="Lone", hp=1, max_hp=1),
    )
    state = WorldState(
        entities={PLAYER: lone},
        areas={"void": void},
        mode_stack=(MODE_EXPLORATION,),
        turn=0,
        rng=Rng.from_seed(0),
    )
    # A grammar entry is a promise that a command can be formed from it.
    assert "move" not in exploration.available_commands(state).verb_names()


def test_the_view_tiers_the_actor_over_the_ground(state: WorldState) -> None:
    frame = exploration.view(state, ())
    assert isinstance(frame.viewport, GridView)
    cell = frame.viewport.cells[1][1]
    assert (cell.ground, cell.actor) == (".", "p")
    assert [actor.id for actor in frame.actors] == [PLAYER, "rock"]
    assert ("#", "wall") in frame.viewport.legend


def test_the_view_narrates_this_turns_events(state: WorldState) -> None:
    _, events = step(state, Move("north"), state.rng)
    assert exploration.view(state, events).messages == ("A wall blocks the way north.",)
