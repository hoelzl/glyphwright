"""Invariants over random walks generated from the frame's own grammar.

The grammar is the generator: an external harness can fuzz the engine without
knowing the rules, which is what makes this a short test. Every invariant is
checked after every step, not at the end of the walk (v0 finding T4).
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from glyphwright.api import Engine, decode_command, reference_pack
from glyphwright.kernel.commands import Command, CommandGrammar, Move
from glyphwright.kernel.events import Event, Moved
from glyphwright.kernel.state import MODE_EXPLORATION, PLAYER, WorldState, fold
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
    assert after.mode_stack == (MODE_EXPLORATION,)
    at = after.entity(PLAYER).at()
    assert at is not None
    space = after.areas[at.area]
    if isinstance(space, GridSpace):
        assert space.terrain(at) != WALL
    for event in events:
        if isinstance(event, Moved) and event.actor == PLAYER:
            assert event.destination == at


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


def test_down_then_up_returns_to_the_hole() -> None:
    engine = _at_the_hole(seed=1)
    hole = engine._state.entity(PLAYER).at()
    assert engine.step(Move("down")).frame.viewport.area == "warren"
    assert engine.step(Move("up")).frame.viewport.area == "village"
    assert engine._state.entity(PLAYER).at() == hole
