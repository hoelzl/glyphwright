"""Menu battle: a mode pushed on the stack, with the shared scheduler running
its initiative queue (design 0003 sections 5.5, 10, 10.1)."""

from __future__ import annotations

import dataclasses

from glyphwright.api import Engine
from glyphwright.content.pack import reference_pack
from glyphwright.frontends import plain
from glyphwright.kernel.commands import Attack, Flee, Look, Move, Use, Wait
from glyphwright.kernel.events import (
    ActorDied,
    AttackMissed,
    DamageDealt,
    ModePopped,
    ModePushed,
)
from glyphwright.kernel.state import PLAYER, fold


def _engine() -> Engine:
    return Engine.new(reference_pack(), seed=3)


def _engaged() -> Engine:
    """Walk south onto (1,2), adjacent to the bandit at (1,3): battle begins."""
    engine = _engine()
    engine.step(Move("south"))
    return engine


def _buffed_engaged(atk: int = 30) -> Engine:
    engine = _engine()
    player = engine._state.entity(PLAYER)
    assert player.actor is not None
    strong = dataclasses.replace(
        player,
        actor=dataclasses.replace(
            player.actor, base_stats=(("atk", atk), ("def", 3), ("spd", 5))
        ),
    )
    engine._state = engine._state.with_entity(strong)
    engine.step(Move("south"))
    return engine


# -- engagement ---------------------------------------------------------------


def test_stepping_next_to_an_engaging_hostile_pushes_battle() -> None:
    engine = _engaged()
    state = engine._state
    assert state.mode == "battle"
    assert state.mode_stack == ("exploration", "battle")


def test_the_push_is_an_event_carrying_the_initiative_order() -> None:
    engine = _engine()
    result = engine.step(Move("south"))
    pushes = [e for e in result.events if isinstance(e, ModePushed)]
    assert len(pushes) == 1
    assert pushes[0].mode == "battle"
    assert sorted(pushes[0].initiative) == ["bandit-1", "player"]
    assert engine._state.initiative == pushes[0].initiative


def test_battle_frames_use_the_menu_viewport() -> None:
    from glyphwright.frames.frame import MenuView

    engine = _engaged()
    frame = engine.frame()
    assert frame.mode == "battle"
    assert isinstance(frame.viewport, MenuView)
    assert "bandit-1" in frame.viewport.combatants
    assert {actor.id for actor in frame.actors} == {"player", "bandit-1"}


def test_battle_grammar_is_attack_use_flee_look() -> None:
    engine = _engaged()
    grammar = engine.frame().commands
    assert "attack" in grammar.verb_names()
    assert "flee" in grammar.verb_names()
    assert "look" in grammar.verb_names()
    assert "move" not in grammar.verb_names()
    assert grammar.domains("attack") == (("bandit-1",),)


def test_exploration_commands_are_rejected_in_battle() -> None:
    engine = _engaged()
    result = engine.step(Move("north"))
    assert result.rejection is not None
    assert engine._state.mode == "battle"


# -- fighting -----------------------------------------------------------------


def test_the_bandit_takes_its_initiative_turn_each_round() -> None:
    engine = _engaged()
    result = engine.step(Attack("bandit-1"))
    if "bandit-1" not in engine._state.entities:
        return  # felled in one blow; victory covered elsewhere
    bandit_acts = [
        e
        for e in result.events
        if isinstance(e, (DamageDealt, AttackMissed)) and e.source == "bandit-1"
    ]
    assert bandit_acts, "the initiative queue must grant the bandit its turn"


def test_victory_pops_battle_with_the_outcome() -> None:
    engine = _buffed_engaged()
    result = engine.step(Attack("bandit-1"))
    assert any(isinstance(e, ActorDied) for e in result.events)
    pops = [e for e in result.events if isinstance(e, ModePopped)]
    assert pops and pops[0].outcome == "victory"
    assert engine._state.mode == "exploration"
    assert engine._state.initiative == ()


def test_defeat_pops_battle_and_sets_the_flag() -> None:
    engine = _engine()
    player = engine._state.entity(PLAYER)
    assert player.actor is not None
    frail = dataclasses.replace(
        player,
        actor=dataclasses.replace(
            player.actor, hp=1, base_stats=(("atk", 0), ("def", 0), ("spd", 5))
        ),
    )
    engine._state = engine._state.with_entity(frail)
    engine.step(Move("south"))
    for _ in range(30):
        if engine._state.flags.get("player-defeated"):
            break
        engine.step(Attack("bandit-1"))
    assert engine._state.flags.get("player-defeated") is True
    assert engine._state.mode == "exploration"
    assert engine.frame().commands.verb_names() == ("look",)


def test_using_a_potion_works_in_battle() -> None:
    """Carry a potion (the player starts wounded at 17/20), then engage."""
    from glyphwright.kernel.commands import Take

    engine = _engine()
    engine.step(Move("east"))
    engine.step(Move("east"))
    engine.step(Take("potion-minor"))
    engine.step(Move("west"))
    engine.step(Move("west"))
    engine.step(Move("south"))  # (1,2) — battle begins
    assert engine._state.mode == "battle"
    grammar = engine.frame().commands
    assert "use" in grammar.verb_names()
    result = engine.step(Use("potion-minor"))
    assert result.accepted
    assert "potion-minor" not in engine._state.entities


# -- fleeing ------------------------------------------------------------------


def test_fleeing_pops_battle_and_escapes() -> None:
    engine = _engaged()
    result = engine.step(Flee())
    assert result.accepted
    pops = [e for e in result.events if isinstance(e, ModePopped)]
    assert pops and pops[0].outcome == "fled"
    assert engine._state.mode == "exploration"
    at = engine._state.entity(PLAYER).at()
    assert at is not None and at.local != "1,2", "fleeing must gain ground"


def test_a_fled_battle_can_reignite_on_recontact() -> None:
    engine = _engaged()
    engine.step(Flee())
    assert engine._state.mode == "exploration"
    # The bandit hunts: within a few waits it closes and battle resumes.
    for _ in range(6):
        if engine._state.mode == "battle":
            break
        engine.step(Wait())
    assert engine._state.mode == "battle"


# -- invariants ---------------------------------------------------------------


def test_battle_events_fold_to_the_successor_state() -> None:
    engine = _engine()
    before = engine._state
    result = engine.step(Move("south"))
    assert fold(before, result.events) == engine._state
    before = engine._state
    result = engine.step(Attack("bandit-1"))
    assert fold(before, result.events) == engine._state


def test_battle_replays_identically() -> None:
    def run() -> list[object]:
        engine = Engine.new(reference_pack(), seed=21)
        engine.step(Move("south"))
        return [engine.step(Attack("bandit-1")).events for _ in range(4)]

    assert run() == run()


def test_look_in_battle_costs_nothing() -> None:
    engine = _engaged()
    turn = engine.frame().turn
    result = engine.step(Look())
    assert result.accepted
    assert engine.frame().turn == turn


def test_battle_frames_render_and_round_trip_in_plain() -> None:
    engine = _engaged()
    frame = engine.frame()
    assert plain.parse(plain.render(frame)) == plain.project(frame)
    assert "battle" in plain.render(frame).splitlines()[0]
