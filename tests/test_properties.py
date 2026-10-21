"""Invariants over random walks generated from the frame's own grammar.

The grammar is the generator: an external harness can fuzz the engine without
knowing the rules, which is what makes this a short test. Every invariant is
checked after every step, not at the end of the walk (v0 finding T4).
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from glyphwright.api import Engine, decode_command, reference_pack
from glyphwright.kernel.commands import Command, CommandGrammar
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


@settings(max_examples=30, deadline=None)
@given(choices=st.lists(st.integers(0, 99), min_size=1, max_size=40))
def test_the_player_reaches_only_floor_tiles(choices: list[int]) -> None:
    engine = Engine.new(reference_pack(), seed=5)
    visited = set()
    for choice in choices:
        options = _options(engine.frame().commands)
        engine.step(options[choice % len(options)])
        visited.add(engine._state.entity(PLAYER).at())
    village = engine._state.areas["village"]
    assert isinstance(village, GridSpace)
    assert all(pos is not None and village.terrain(pos) == "." for pos in visited)
