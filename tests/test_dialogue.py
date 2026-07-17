"""Dialogue: trees are content, lines and choices are events, and a
conversation is an ordinary mode on the stack (design 0003 §10.2)."""

from __future__ import annotations

from glyphwright.api import Engine
from glyphwright.content.pack import reference_pack
from glyphwright.frames.frame import DialogueView
from glyphwright.kernel.commands import Choose, Look, Move, Talk, Wait
from glyphwright.kernel.events import (
    ChoiceOffered,
    DialogueLine,
    FlagSet,
    ModePopped,
    ModePushed,
)
from glyphwright.kernel.state import PLAYER, fold


def _engine() -> Engine:
    return Engine.new(reference_pack(), seed=23)


def _at_innkeeper() -> Engine:
    """Walk into the common room, where the innkeeper waits."""
    engine = _engine()
    for _ in range(6):
        engine.step(Move("east"))
    engine.step(Move("enter"))
    return engine


def _talking() -> Engine:
    engine = _at_innkeeper()
    engine.step(Talk("innkeeper"))
    return engine


# -- starting a conversation --------------------------------------------------


def test_talk_is_advertised_when_a_speaker_is_in_reach() -> None:
    engine = _engine()
    assert "talk" not in engine.frame().commands.verb_names()
    engine = _at_innkeeper()
    assert engine.frame().commands.domains("talk") == (("innkeeper",),)


def test_talking_pushes_dialogue_with_line_and_choices() -> None:
    engine = _at_innkeeper()
    result = engine.step(Talk("innkeeper"))
    assert result.accepted
    kinds = [type(e) for e in result.events]
    assert ModePushed in kinds and DialogueLine in kinds and ChoiceOffered in kinds
    assert engine._state.mode == "dialogue"


def test_dialogue_frames_use_the_dialogue_viewport() -> None:
    engine = _talking()
    frame = engine.frame()
    assert isinstance(frame.viewport, DialogueView)
    assert frame.viewport.speaker == "innkeeper"
    assert frame.viewport.text
    assert len(frame.viewport.choices) >= 2


def test_the_grammar_offers_exactly_the_choices() -> None:
    engine = _talking()
    frame = engine.frame()
    assert isinstance(frame.viewport, DialogueView)
    expected = tuple(str(i + 1) for i in range(len(frame.viewport.choices)))
    assert frame.commands.domains("choose") == (expected,)
    assert "move" not in frame.commands.verb_names()


# -- choosing -----------------------------------------------------------------


def test_a_choice_can_set_a_flag_and_continue() -> None:
    engine = _talking()
    frame = engine.frame()
    assert isinstance(frame.viewport, DialogueView)
    # Choice 1 asks about the cellar: it sets the rumor flag and talks on.
    result = engine.step(Choose("1"))
    assert result.accepted
    assert any(isinstance(e, FlagSet) for e in result.events)
    assert engine._state.flags.get("heard-cellar-rumor") is True
    assert engine._state.mode == "dialogue"


def test_the_farewell_choice_pops_the_dialogue() -> None:
    engine = _talking()
    frame = engine.frame()
    assert isinstance(frame.viewport, DialogueView)
    farewell = str(len(frame.viewport.choices))  # the last choice ends it
    result = engine.step(Choose(farewell))
    pops = [e for e in result.events if isinstance(e, ModePopped)]
    assert pops and pops[0].mode == "dialogue"
    assert engine._state.mode == "exploration"
    assert engine._state.focus is None


def test_an_out_of_range_choice_is_rejected() -> None:
    engine = _talking()
    result = engine.step(Choose("9"))
    assert result.rejection is not None
    assert result.rejection.reason == "no_such_choice"
    assert engine._state.mode == "dialogue"


def test_world_verbs_are_wrong_mode_during_dialogue() -> None:
    engine = _talking()
    result = engine.step(Move("down"))
    assert result.rejection is not None
    assert result.rejection.reason == "wrong_mode"


def test_passive_hostiles_do_not_act_while_talking() -> None:
    """The world does not freeze during a conversation — but an unprovoked
    hostile far away has no reason to act either."""
    engine = _talking()
    before = {
        entity_id: entity.at() for entity_id, entity in engine._state.entities.items()
    }
    engine.step(Choose("1"))
    after = {
        entity_id: entity.at() for entity_id, entity in engine._state.entities.items()
    }
    assert before == after, "passive hostiles have no reason to move"


# -- determinism --------------------------------------------------------------


def test_dialogue_folds_and_replays() -> None:
    engine = _at_innkeeper()
    before = engine._state
    result = engine.step(Talk("innkeeper"))
    assert fold(before, result.events) == engine._state

    def run() -> list[object]:
        e = Engine.new(reference_pack(), seed=41)
        for _ in range(6):
            e.step(Move("east"))
        e.step(Move("enter"))
        e.step(Talk("innkeeper"))
        e.step(Choose("1"))
        return [e.step(Choose("2")).events]

    assert run() == run()


def test_look_during_dialogue_costs_nothing() -> None:
    engine = _talking()
    turn = engine.frame().turn
    assert engine.step(Look()).accepted
    assert engine.frame().turn == turn
    assert engine.step(Wait()).rejection is not None, "no waiting mid-sentence"


def test_a_dialogue_without_a_reachable_farewell_is_unrepresentable() -> None:
    import pytest

    from glyphwright.world.entities import Dialogue, DialogueChoice, DialogueNode

    with pytest.raises(ValueError, match="farewell"):
        Dialogue(
            root="a",
            nodes=(
                DialogueNode(
                    id="a",
                    line="Round",
                    choices=(DialogueChoice(text="and round", next="b"),),
                ),
                DialogueNode(
                    id="b",
                    line="we go",
                    choices=(DialogueChoice(text="again", next="a"),),
                ),
            ),
        )


def test_hostiles_keep_acting_while_the_player_talks() -> None:
    """Talking does not stop the world: a hostile that reaches the player
    mid-conversation interrupts it with a battle."""
    from glyphwright.world.entities import Actor, AiBehavior, Entity, Position
    from glyphwright.world.roomgraph import RoomGraphSpace

    engine = _at_innkeeper()
    inn = engine._state.areas["inn"]
    assert isinstance(inn, RoomGraphSpace)
    brute = Entity(
        id="cellar-brute",
        position=Position(at=inn.pos("cellar")),
        actor=Actor(name="Brute", hp=8, max_hp=8, base_stats=(("atk", 3),)),
        ai=AiBehavior(hostile=True, engages=True),
    )
    engine._state = engine._state.with_entity(brute)
    from glyphwright.kernel.events import FlagSet as Flag
    from glyphwright.kernel.state import fold as _fold

    engine._state = _fold(engine._state, (Flag(flag="aggro:cellar-brute", value=True),))
    engine.step(Talk("innkeeper"))
    assert engine._state.mode == "dialogue"
    # The brute climbs from the cellar and engages: the conversation is
    # interrupted by a battle pushed on top of it.
    for _ in range(4):
        if engine._state.mode == "battle":
            break
        engine.step(Choose("2"))
    assert engine._state.mode == "battle"
    assert engine._state.mode_stack == ("exploration", "dialogue", "battle")
    assert engine._state.focus is not None, (
        "the conversation's cursor must survive beneath the battle"
    )


def test_talking_again_after_farewell_restarts_the_tree() -> None:
    engine = _talking()
    frame = engine.frame()
    assert isinstance(frame.viewport, DialogueView)
    engine.step(Choose(str(len(frame.viewport.choices))))
    assert engine._state.mode == "exploration"
    result = engine.step(Talk("innkeeper"))
    assert result.accepted
    assert engine._state.mode == "dialogue"
    player = engine._state.entity(PLAYER)
    assert player.actor is not None
