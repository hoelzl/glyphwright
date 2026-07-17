"""Invariants over random walks generated from the frame's own grammar.

The grammar is the generator: an external harness can fuzz the engine without
knowing the rules, which is exactly what makes this a short test (design 0003
sections 6 and 17).
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from glyphwright.api import Engine
from glyphwright.content.pack import reference_pack
from glyphwright.kernel.commands import Command, Equip, Look, Move, Take, Use, Wait
from glyphwright.kernel.events import Moved
from glyphwright.kernel.state import PLAYER, WorldState
from glyphwright.world.grid import WALL, GridSpace

_BUILDERS: tuple[tuple[str, type], ...] = (
    ("move", Move),
    ("take", Take),
    ("use", Use),
    ("equip", Equip),
)


def _options(engine: Engine) -> list[Command]:
    """Every command the frame's grammar currently advertises."""
    grammar = engine.frame().commands
    options: list[Command] = [Look(), Wait()]
    for verb, builder in _BUILDERS:
        if verb in grammar.verb_names():
            options.extend(builder(argument) for argument in grammar.domains(verb)[0])
    return options


def _walk(engine: Engine, choices: list[int], length: int) -> None:
    """Drive the engine using only commands its own grammar advertises."""
    for index in range(length):
        options = _options(engine)
        command = options[choices[index % len(choices)] % len(options)]
        result = engine.step(command)
        assert result.rejection is None, (
            f"a command the grammar advertised was rejected: {result.rejection}"
        )


@settings(max_examples=40, deadline=None)
@given(choices=st.lists(st.integers(0, 99), min_size=1, max_size=30))
def test_grammar_commands_are_never_rejected(choices: list[int]) -> None:
    _walk(Engine.new(reference_pack(), seed=4), choices, len(choices))


@settings(max_examples=40, deadline=None)
@given(choices=st.lists(st.integers(0, 99), min_size=1, max_size=30))
def test_the_player_never_stands_in_a_wall(choices: list[int]) -> None:
    engine = Engine.new(reference_pack(), seed=5)
    _walk(engine, choices, len(choices))
    state = engine._state
    at = state.entity(PLAYER).at()
    assert at is not None
    space = state.areas[at.area]
    assert isinstance(space, GridSpace)
    assert space.terrain(at) != WALL


@settings(max_examples=40, deadline=None)
@given(choices=st.lists(st.integers(0, 99), min_size=1, max_size=30))
def test_the_player_never_leaves_the_area(choices: list[int]) -> None:
    engine = Engine.new(reference_pack(), seed=6)
    _walk(engine, choices, len(choices))
    state = engine._state
    at = state.entity(PLAYER).at()
    assert at is not None
    space = state.areas[at.area]
    assert isinstance(space, GridSpace)
    assert space.contains(at)


@settings(max_examples=40, deadline=None)
@given(choices=st.lists(st.integers(0, 99), min_size=1, max_size=30))
def test_the_mode_stack_never_underflows(choices: list[int]) -> None:
    engine = Engine.new(reference_pack(), seed=7)
    _walk(engine, choices, len(choices))
    assert engine._state.mode_stack == ("exploration",)


@settings(max_examples=40, deadline=None)
@given(choices=st.lists(st.integers(0, 99), min_size=1, max_size=30))
def test_the_turn_counter_only_ever_rises(choices: list[int]) -> None:
    engine = Engine.new(reference_pack(), seed=8)
    turn = engine.frame().turn
    for index in range(len(choices)):
        _walk(engine, choices[index : index + 1], 1)
        assert engine.frame().turn >= turn
        turn = engine.frame().turn


@settings(max_examples=40, deadline=None)
@given(choices=st.lists(st.integers(0, 99), min_size=1, max_size=30))
def test_every_move_lands_where_its_event_says(choices: list[int]) -> None:
    engine = Engine.new(reference_pack(), seed=9)
    for index in range(len(choices)):
        options = _options(engine)
        result = engine.step(options[choices[index] % len(options)])
        for event in result.events:
            if isinstance(event, Moved):
                assert engine._state.entity(PLAYER).at() == event.destination


def _held_anywhere(state: WorldState) -> list[str]:
    return [item for entity in state.entities.values() for item in entity.carries()]


@settings(max_examples=40, deadline=None)
@given(choices=st.lists(st.integers(0, 99), min_size=1, max_size=30))
def test_hp_stays_within_bounds(choices: list[int]) -> None:
    engine = Engine.new(reference_pack(), seed=10)
    for index in range(len(choices)):
        _walk(engine, choices[index : index + 1], 1)
        for entity in engine._state.entities.values():
            if entity.actor is not None:
                assert 0 <= entity.actor.hp <= entity.actor.max_hp


@settings(max_examples=40, deadline=None)
@given(choices=st.lists(st.integers(0, 99), min_size=1, max_size=30))
def test_items_are_conserved_until_consumed(choices: list[int]) -> None:
    """An item is on the ground or carried by exactly one holder — never both,
    never duplicated — until consumption removes it entirely (0003 section 17)."""
    engine = Engine.new(reference_pack(), seed=11)
    initial_items = {
        entity.id
        for entity in engine._state.entities.values()
        if entity.item is not None
    }
    for index in range(len(choices)):
        _walk(engine, choices[index : index + 1], 1)
        state = engine._state
        held = _held_anywhere(state)
        assert len(held) == len(set(held)), "an item may have only one holder"
        for item_id in held:
            assert item_id in state.entities
            assert state.entity(item_id).at() is None, (
                "a carried item may not also lie on the ground"
            )
        surviving = {
            entity.id for entity in state.entities.values() if entity.item is not None
        }
        assert surviving <= initial_items, "items cannot appear from nowhere"


@settings(max_examples=40, deadline=None)
@given(choices=st.lists(st.integers(0, 99), min_size=1, max_size=30))
def test_equipment_always_points_at_carried_items(choices: list[int]) -> None:
    engine = Engine.new(reference_pack(), seed=12)
    for index in range(len(choices)):
        _walk(engine, choices[index : index + 1], 1)
        for entity in engine._state.entities.values():
            if entity.equipment is None:
                continue
            for _, item_id in entity.equipment.slots:
                assert item_id in entity.carries(), (
                    "equipment must reference the wearer's own inventory"
                )
