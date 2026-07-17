"""Exploration combat and the shared scheduler (design 0003 sections 5.5, 10.1
appendix A/B): the player attacks visible hostiles, and AI actors take their
turns inside ``step`` so NPC behavior replays exactly."""

from __future__ import annotations

import dataclasses

from glyphwright.api import Engine
from glyphwright.content.pack import reference_pack
from glyphwright.kernel.commands import Attack, Move, Wait
from glyphwright.kernel.events import (
    ActorDied,
    AttackMissed,
    DamageDealt,
    FlagSet,
    TurnAdvanced,
)
from glyphwright.kernel.state import PLAYER, fold


def _engine() -> Engine:
    return Engine.new(reference_pack(), seed=1)


def _next_to_goblin() -> Engine:
    """Walk the player from (1,1) to (2,2), adjacent to the goblin at (2,3)."""
    engine = _engine()
    engine.step(Move("east"))
    engine.step(Move("south"))
    return engine


def _goblin_hp(engine: Engine) -> int:
    goblin = engine._state.entities.get("goblin-1")
    if goblin is None or goblin.actor is None:
        return 0
    return goblin.actor.hp


# -- the attack command -------------------------------------------------------


def test_attack_is_advertised_only_at_melee_range() -> None:
    engine = _engine()
    assert "attack" not in engine.frame().commands.verb_names()
    engine = _next_to_goblin()
    assert engine.frame().commands.domains("attack") == (("goblin-1",),)


def test_attacking_produces_damage_or_a_miss_and_spends_the_turn() -> None:
    engine = _next_to_goblin()
    result = engine.step(Attack("goblin-1"))
    assert result.accepted
    kinds = [type(event) for event in result.events]
    assert DamageDealt in kinds or AttackMissed in kinds
    assert kinds[-1] == TurnAdvanced
    assert result.frame.turn == 3


def test_damage_lands_on_the_target() -> None:
    engine = _next_to_goblin()
    before = _goblin_hp(engine)
    for _ in range(3):
        result = engine.step(Attack("goblin-1"))
        hits = [e for e in result.events if isinstance(e, DamageDealt)]
        for hit in hits:
            if hit.target == "goblin-1":
                assert hit.amount >= 1
        if _goblin_hp(engine) == 0:
            break
    assert _goblin_hp(engine) <= before


def test_a_dead_goblin_is_removed_and_leaves_the_grammar() -> None:
    engine = _next_to_goblin()
    for _ in range(20):
        if "goblin-1" not in engine._state.entities:
            break
        engine.step(Attack("goblin-1"))
    assert "goblin-1" not in engine._state.entities
    assert "attack" not in engine.frame().commands.verb_names()


def test_killing_emits_actor_died_after_the_fatal_damage() -> None:
    engine = _next_to_goblin()
    for _ in range(20):
        result = engine.step(Attack("goblin-1"))
        if any(isinstance(e, ActorDied) for e in result.events):
            kinds = [type(e) for e in result.events]
            assert kinds.index(DamageDealt) < kinds.index(ActorDied)
            return
    raise AssertionError("the goblin never died in twenty attacks")


def test_attacking_something_absent_is_rejected() -> None:
    engine = _engine()
    result = engine.step(Attack("balrog"))
    assert result.rejection is not None
    assert result.rejection.reason == "no_such_target"
    assert engine.frame().turn == 0


# -- the scheduler: AI turns happen inside step -------------------------------


def test_an_attacked_goblin_fights_back_within_the_same_step() -> None:
    engine = _next_to_goblin()
    result = engine.step(Attack("goblin-1"))
    if "goblin-1" not in engine._state.entities:
        return  # killed outright; nothing left to fight back
    goblin_acts = [
        e
        for e in result.events
        if isinstance(e, (DamageDealt, AttackMissed)) and e.source == "goblin-1"
    ]
    assert goblin_acts, "the scheduler must grant the goblin its turn"


def test_a_passive_goblin_ignores_commands_elsewhere() -> None:
    engine = _engine()
    result = engine.step(Move("east"))
    assert all(not isinstance(e, (DamageDealt, AttackMissed)) for e in result.events), (
        "an unprovoked goblin far away must not act"
    )


def test_walking_next_to_the_goblin_provokes_it() -> None:
    engine = _next_to_goblin()
    assert engine._state.flags.get("aggro:goblin-1") is True, (
        "stepping adjacent must wake a hostile"
    )
    result = engine.step(Wait())
    goblin_acts = [
        e
        for e in result.events
        if isinstance(e, (DamageDealt, AttackMissed)) and e.source == "goblin-1"
    ]
    assert goblin_acts, "an awake adjacent hostile must fight"


def test_an_aggroed_goblin_chases_the_player() -> None:
    engine = _next_to_goblin()
    engine.step(Move("north"))
    engine.step(Move("east"))
    goblin = engine._state.entities.get("goblin-1")
    assert goblin is not None
    at = goblin.at()
    assert at is not None
    assert at.local != "2,3", "an aggroed hostile must give chase"


def test_player_hp_never_goes_below_zero() -> None:
    engine = _next_to_goblin()
    for _ in range(30):
        engine.step(Wait())
    player = engine._state.entity(PLAYER).actor
    assert player is not None and player.hp >= 0


# -- determinism and fold equivalence ----------------------------------------


def test_combat_replays_identically() -> None:
    def run() -> list[object]:
        engine = Engine.new(reference_pack(), seed=77)
        engine.step(Move("east"))
        engine.step(Move("south"))
        return [engine.step(Attack("goblin-1")).events for _ in range(5)]

    assert run() == run()


def test_combat_events_fold_to_the_successor_state() -> None:
    engine = _next_to_goblin()
    before = engine._state
    result = engine.step(Attack("goblin-1"))
    folded = fold(before, result.events)
    assert folded.entities == engine._state.entities
    assert folded.turn == engine._state.turn


def test_combat_advances_the_rng_cursor() -> None:
    engine = _next_to_goblin()
    before = engine._state.rng
    engine.step(Attack("goblin-1"))
    assert engine._state.rng != before, "a combat roll must land in world state"


def test_combat_messages_are_rendered() -> None:
    engine = _next_to_goblin()
    result = engine.step(Attack("goblin-1"))
    assert result.frame.messages, "combat must narrate its events"


def test_defeat_sets_the_flag_and_stops_the_fight() -> None:
    """Interim defeat semantics until menu battle lands (slice 3B): the world
    flag flips, and the grammar collapses to observation."""
    engine = _next_to_goblin()
    player = engine._state.entity(PLAYER)
    assert player.actor is not None
    weakened = dataclasses.replace(
        player, actor=dataclasses.replace(player.actor, hp=1, base_stats=(("atk", 0),))
    )
    engine._state = engine._state.with_entity(weakened)
    for _ in range(50):
        if engine._state.flags.get("player-defeated"):
            break
        engine.step(Wait())
    assert engine._state.flags.get("player-defeated") is True
    assert engine.frame().commands.verb_names() == ("look",)
