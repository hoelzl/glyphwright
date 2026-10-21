"""Menu battle: a mode pushed by a hostile, with the scheduler running its
initiative order inside ``step``."""

from __future__ import annotations

import dataclasses

from hypothesis import given, settings
from hypothesis import strategies as st

from glyphwright.api import Engine, reference_pack
from glyphwright.frames.frame import MenuView
from glyphwright.frontends import plain
from glyphwright.kernel.commands import (
    Attack,
    Command,
    Flee,
    Look,
    Move,
    Take,
    Use,
    Wait,
)
from glyphwright.kernel.events import (
    ActorDied,
    AttackMissed,
    DamageDealt,
    Defeated,
    Event,
    Healed,
    ModePopped,
    ModePushed,
    Moved,
    Provoked,
)
from glyphwright.kernel.state import MODE_BATTLE, MODE_EXPLORATION, PLAYER

TO_THE_GOBLIN = (Move("east"), Move("south"))


def _engine(seed: int = 424242) -> Engine:
    return Engine.new(reference_pack(), seed=seed)


def _play(engine: Engine, commands: tuple[Command, ...]) -> tuple[Event, ...]:
    events: list[Event] = []
    for command in commands:
        result = engine.step(command)
        assert result.accepted, (command, result.rejection)
        events.extend(result.events)
    return tuple(events)


def _adjust(engine: Engine, entity_id: str, **changes: object) -> None:
    """Rewrite one actor's numbers, for scenarios the dice rarely produce."""
    entity = engine._state.entity(entity_id)
    assert entity.actor is not None
    actor = dataclasses.replace(entity.actor, **changes)  # type: ignore[arg-type]
    engine._state = engine._state.with_entity(dataclasses.replace(entity, actor=actor))


def _strikes_by(events: tuple[Event, ...], source: str) -> int:
    return sum(
        isinstance(event, DamageDealt | AttackMissed) and event.source == source
        for event in events
    )


def test_stepping_next_to_a_hostile_starts_a_battle() -> None:
    engine = _engine()
    events = _play(engine, TO_THE_GOBLIN)
    pushed = next(event for event in events if isinstance(event, ModePushed))
    assert pushed.mode == MODE_BATTLE
    assert set(pushed.initiative) == {PLAYER, "goblin-1"}
    assert Provoked(actor="goblin-1") in events
    assert engine.frame().mode == MODE_BATTLE


def test_a_battle_frame_names_the_combatants_instead_of_a_map() -> None:
    engine = _engine()
    _play(engine, TO_THE_GOBLIN)
    frame = engine.frame()
    assert isinstance(frame.viewport, MenuView)
    assert set(frame.viewport.combatants) == {PLAYER, "goblin-1"}
    assert frame.commands.verb_names() == ("attack", "flee", "look")
    assert frame.commands.domains("attack") == (("goblin-1",),)


def test_moving_in_a_battle_is_rejected_as_the_wrong_mode() -> None:
    engine = _engine()
    _play(engine, TO_THE_GOBLIN)
    rejection = engine.step(Move("north")).rejection
    assert rejection is not None and rejection.reason == "wrong_mode"


def test_attacking_someone_not_in_the_fight_is_rejected() -> None:
    engine = _engine()
    _play(engine, TO_THE_GOBLIN)
    rejection = engine.step(Attack("bandit-1")).rejection
    assert rejection is not None
    assert (rejection.reason, rejection.hint) == (
        "no_such_target",
        "you can attack: goblin-1",
    )


def test_an_aggroed_hostile_nearby_joins_the_battle() -> None:
    engine = _engine()
    goblin = engine._state.entity("goblin-1")
    assert goblin.ai is not None
    awake = dataclasses.replace(goblin, ai=dataclasses.replace(goblin.ai, aggroed=True))
    engine._state = engine._state.with_entity(awake)
    # Stepping south lands next to the bandit, which starts the battle.
    events = _play(engine, (Move("south"),))
    pushed = next(event for event in events if isinstance(event, ModePushed))
    assert set(pushed.initiative) == {PLAYER, "bandit-1", "goblin-1"}


@settings(max_examples=40, deadline=None)
@given(seed=st.integers(0, 2**32))
def test_foes_that_outroll_the_player_strike_first(seed: int) -> None:
    engine = _engine(seed)
    events = _play(engine, TO_THE_GOBLIN)
    pushed = next(event for event in events if isinstance(event, ModePushed))
    ahead = pushed.initiative.index(PLAYER)
    assert _strikes_by(events, "goblin-1") == ahead


def test_the_foe_takes_its_turn_after_every_attack() -> None:
    engine = _engine()
    _play(engine, TO_THE_GOBLIN)
    _adjust(engine, "goblin-1", hp=99, max_hp=99)
    for _ in range(3):
        events = _play(engine, (Attack("goblin-1"),))
        assert _strikes_by(events, PLAYER) == 1
        assert _strikes_by(events, "goblin-1") == 1


def test_killing_the_last_foe_wins_the_battle() -> None:
    engine = _engine()
    _play(engine, TO_THE_GOBLIN)
    _adjust(engine, PLAYER, base_stats=(("atk", 40),))
    _adjust(engine, "goblin-1", hp=1)
    result = engine.step(Attack("goblin-1"))
    assert result.events[-2] == ModePopped(mode=MODE_BATTLE, outcome="victory")
    assert ActorDied(actor="goblin-1") in result.events
    assert result.frame.mode == MODE_EXPLORATION
    assert result.frame.messages[-1] == "You are victorious!"


def test_defeat_ends_the_battle_and_leaves_only_look() -> None:
    engine = _engine()
    _adjust(engine, PLAYER, hp=1, base_stats=())
    _adjust(engine, "goblin-1", base_stats=(("atk", 40),))
    events = _play(engine, TO_THE_GOBLIN)
    while engine.frame().mode == MODE_BATTLE:
        events = _play(engine, (Attack("goblin-1"),))
    assert Defeated(actor=PLAYER) in events
    assert events[-2] == ModePopped(mode=MODE_BATTLE, outcome="defeat")
    assert engine.frame().commands.verb_names() == ("look",)
    for command in (Move("north"), Attack("goblin-1"), Flee()):
        rejection = engine.step(command).rejection
        assert rejection is not None and rejection.reason == "defeated"
    assert engine.step(Look()).accepted


def test_a_potion_works_in_battle() -> None:
    engine = _engine()
    _play(engine, (Move("east"), Move("east"), Take("potion-minor"), Move("west")))
    _play(engine, (Move("south"),))
    assert engine.frame().mode == MODE_BATTLE
    assert engine.frame().commands.domains("use") == (("potion-minor",),)
    events = _play(engine, (Use("potion-minor"),))
    assert any(isinstance(event, Healed) for event in events)


def test_a_flee_breaks_contact_and_ends_the_battle() -> None:
    engine = _engine()
    _play(engine, TO_THE_GOBLIN)
    events = _play(engine, (Flee(),))
    assert ModePopped(mode=MODE_BATTLE, outcome="fled") in events
    assert engine.frame().mode == MODE_EXPLORATION
    escape = next(e for e in events if isinstance(e, Moved) and e.actor == PLAYER)
    assert escape.destination != escape.origin


def test_a_fled_foe_gives_chase_and_can_start_the_battle_again() -> None:
    engine = _engine()
    _play(engine, TO_THE_GOBLIN)
    events = _play(engine, (Flee(),))
    goblin = engine._state.entity("goblin-1")
    assert goblin.ai is not None and goblin.ai.aggroed
    assert any(isinstance(e, Moved) and e.actor == "goblin-1" for e in events)
    for _ in range(5):
        if engine.frame().mode == MODE_BATTLE:
            break
        _play(engine, (Wait(),))
    assert engine.frame().mode == MODE_BATTLE


def test_look_in_battle_costs_nothing() -> None:
    engine = _engine()
    _play(engine, TO_THE_GOBLIN)
    turn = engine.frame().turn
    assert _play(engine, (Look(),)) == ()
    assert engine.frame().turn == turn


def test_a_battle_replays_identically() -> None:
    script = (*TO_THE_GOBLIN, Attack("goblin-1"), Attack("goblin-1"))
    assert _play(_engine(7), script) == _play(_engine(7), script)


def test_battle_frames_render_and_round_trip_in_plain() -> None:
    engine = _engine()
    frame = engine.step(TO_THE_GOBLIN[0]).frame
    frame = engine.step(TO_THE_GOBLIN[1]).frame
    text = plain.render(frame)
    assert text.splitlines()[1].startswith("[initiative ")
    assert plain.parse(text) == plain.project(frame)
