"""Invariants over random walks generated from the frame's own grammar.

The grammar is the generator: an external harness can fuzz the engine without
knowing the rules, which is what makes this a short test. Every invariant is
checked after every step, not at the end of the walk (v0 finding T4).
"""

from __future__ import annotations

import dataclasses

from hypothesis import given, settings
from hypothesis import strategies as st

from glyphwright.api import Engine, decode_command, reference_pack
from glyphwright.kernel.commands import Command, CommandGrammar, Move, Take
from glyphwright.kernel.events import Defeated, Event, ModePopped, Moved, TurnAdvanced
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
    _check_combat(after, events)


def _check_combat(state: WorldState, events: tuple[Event, ...]) -> None:
    """The dead leave, the order names only the living, and defeat ends play."""
    assert all(combatant in state.entities for combatant in state.initiative)
    if state.mode == MODE_BATTLE:
        assert PLAYER in state.initiative
    for entity in state.entities.values():
        if entity.ai is not None and entity.actor is not None:
            assert entity.actor.hp > 0, f"{entity.id} is dead but still here"
    if state.defeated:
        assert state.mode == MODE_EXPLORATION
        assert state.mode_stack == (MODE_EXPLORATION,)
    # Nobody acts after the player falls; the round only closes.
    fallen = [i for i, event in enumerate(events) if isinstance(event, Defeated)]
    if fallen:
        assert all(
            isinstance(event, ModePopped | TurnAdvanced)
            for event in events[fallen[0] + 1 :]
        )


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


def _in_battle(seed: int, *, doomed: bool = False) -> Engine:
    """An engine whose player has just stepped next to the goblin.

    ``doomed`` weakens the player and strengthens the goblin, so walks reach
    defeat (v0 finding T4: no v0 walk ever did).
    """
    engine = Engine.new(reference_pack(), seed=seed)
    if doomed:
        for entity_id, changes in (
            (PLAYER, {"hp": 2, "base_stats": ()}),
            ("goblin-1", {"base_stats": (("atk", 12),)}),
        ):
            entity = engine._state.entity(entity_id)
            assert entity.actor is not None
            actor = dataclasses.replace(entity.actor, **changes)
            engine._state = engine._state.with_entity(
                dataclasses.replace(entity, actor=actor)
            )
    for token in ("east", "south"):
        assert engine.step(Move(token)).accepted
    return engine


@settings(max_examples=40, deadline=None)
@given(
    seed=st.integers(0, 2**32),
    choices=st.lists(st.integers(0, 99), min_size=1, max_size=30),
)
def test_battle_walks_keep_every_invariant(seed: int, choices: list[int]) -> None:
    _walk(_in_battle(seed), choices)


@settings(max_examples=40, deadline=None)
@given(
    seed=st.integers(0, 2**32),
    choices=st.lists(st.integers(0, 99), min_size=5, max_size=30),
)
def test_walks_toward_defeat_keep_every_invariant(
    seed: int, choices: list[int]
) -> None:
    engine = _in_battle(seed, doomed=True)
    _walk(engine, choices)


def test_a_doomed_walk_does_reach_defeat() -> None:
    """The steering works: the doomed setup is not vacuous."""
    engine = _in_battle(1, doomed=True)
    _walk(engine, [0] * 30)
    assert engine._state.defeated
