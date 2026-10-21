"""Invariants over random walks generated from the frame's own grammar.

The grammar is the generator: an external harness can fuzz the engine without
knowing the rules, which is what makes this a short test. Every invariant is
checked after every step, not at the end of the walk (v0 finding T4).
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from glyphwright.api import Engine, decode_command, reference_pack
from glyphwright.kernel.commands import Command, CommandGrammar, Move, Take
from glyphwright.kernel.events import Event, Moved
from glyphwright.kernel.state import (
    MODE_BATTLE,
    MODE_EXPLORATION,
    PLAYER,
    WorldState,
    fold,
)
from glyphwright.world.grid import WALL, GridSpace


def _options(grammar: CommandGrammar) -> list[Command]:
    """Every command the grammar advertises, formed through the decoder.

    Building commands from text keeps this generic over arity: a later verb
    joins the walk without a change here.
    """
    options: list[Command] = []
    for verb in grammar.verb_names():
        texts = [verb]
        for domain in grammar.domains(verb):
            texts = [f"{text} {argument}" for text in texts for argument in domain]
        for text in texts:
            command = decode_command(text)
            assert command is not None, f"the grammar advertised {text!r}"
            options.append(command)
    return options


def _check_step(
    before: WorldState, after: WorldState, events: tuple[Event, ...]
) -> None:
    # v0 finding T1: compare whole states, not a few fields.
    assert fold(before, events) == after
    assert after.turn in (before.turn, before.turn + 1)
    # v0 finding T4: check the stack's shape, not a fixed list of stacks.
    assert after.mode_stack[0] == MODE_EXPLORATION
    assert after.mode_stack[1:] in ((), (MODE_BATTLE,))
    assert bool(after.initiative) == (after.mode == MODE_BATTLE)
    at = after.entity(PLAYER).at()
    assert at is not None
    space = after.areas[at.area]
    if isinstance(space, GridSpace):
        assert space.terrain(at) != WALL
    for event in events:
        if isinstance(event, Moved) and event.actor == PLAYER:
            assert event.destination == at
    _check_items(after)


def _check_items(state: WorldState) -> None:
    """Items are conserved: on the ground, or carried by exactly one actor."""
    holders: dict[str, list[str]] = {}
    for entity in state.entities.values():
        if entity.actor is not None:
            assert 0 <= entity.actor.hp <= entity.actor.max_hp, entity.id
        for item_id in entity.carries():
            holders.setdefault(item_id, []).append(entity.id)
            assert state.entity(item_id).at() is None, (
                f"{item_id} is carried and placed"
            )
        worn = entity.equipment.equipped_items() if entity.equipment else ()
        assert set(worn) <= set(entity.carries()), f"{entity.id} wears what it lacks"
    for entity in state.entities.values():
        if entity.item is not None:
            placed = entity.at() is not None
            assert placed != (entity.id in holders), entity.id
            assert len(holders.get(entity.id, [])) <= 1, entity.id


def _walk(engine: Engine, choices: list[int]) -> None:
    """Drive the engine using only commands its own grammar advertises."""
    for choice in choices:
        options = _options(engine.frame().commands)
        command = options[choice % len(options)]
        before = engine._state
        result = engine.step(command)
        assert result.rejection is None, (
            f"a command the grammar advertised was rejected: {result.rejection}"
        )
        _check_step(before, engine._state, result.events)


@settings(max_examples=60, deadline=None)
@given(
    seed=st.integers(0, 2**32),
    choices=st.lists(st.integers(0, 99), min_size=1, max_size=40),
)
def test_grammar_walks_keep_every_invariant_at_every_step(
    seed: int, choices: list[int]
) -> None:
    _walk(Engine.new(reference_pack(), seed=seed), choices)


_TO_THE_HOLE = ("east",) * 6 + ("south",) * 2


def _at_the_hole(seed: int) -> Engine:
    """An engine whose player stands on the village's hole down to the warren.

    Random walks from the start rarely get this far, so portal walks start here.
    """
    engine = Engine.new(reference_pack(), seed=seed)
    for token in _TO_THE_HOLE:
        assert engine.step(Move(token)).accepted
    assert "down" in engine.frame().commands.domains("move")[0]
    return engine


@settings(max_examples=40, deadline=None)
@given(choices=st.lists(st.integers(0, 99), min_size=1, max_size=40))
def test_walks_through_the_portals_keep_every_invariant(choices: list[int]) -> None:
    _walk(_at_the_hole(seed=6), choices)


def _with_the_items(seed: int) -> Engine:
    """An engine whose player has taken the potion and the sword."""
    engine = Engine.new(reference_pack(), seed=seed)
    script = (
        [Move("east")] * 2
        + [Take("potion-minor")]
        + [Move("east")] * 3
        + [Move("south")] * 2
        + [Take("iron-sword")]
    )
    for command in script:
        assert engine.step(command).accepted, command
    return engine


@settings(max_examples=40, deadline=None)
@given(choices=st.lists(st.integers(0, 99), min_size=1, max_size=30))
def test_walks_with_items_keep_every_invariant(choices: list[int]) -> None:
    _walk(_with_the_items(seed=7), choices)


def test_down_then_up_returns_to_the_hole() -> None:
    engine = _at_the_hole(seed=1)
    hole = engine._state.entity(PLAYER).at()
    assert engine.step(Move("down")).frame.viewport.area == "warren"
    assert engine.step(Move("up")).frame.viewport.area == "village"
    assert engine._state.entity(PLAYER).at() == hole
