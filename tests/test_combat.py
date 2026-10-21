"""The strike and the initiative roll."""

from __future__ import annotations

import dataclasses

from hypothesis import given
from hypothesis import strategies as st

from glyphwright.api import Engine, reference_pack
from glyphwright.effects.combat import (
    hostile_actors,
    melee_adjacent,
    roll_initiative,
    strike,
)
from glyphwright.kernel.events import ActorDied, AttackMissed, DamageDealt, Defeated
from glyphwright.kernel.rng import Rng
from glyphwright.kernel.state import PLAYER, WorldState
from glyphwright.world.space import PosId


def _state() -> WorldState:
    return Engine.new(reference_pack(), seed=1)._state


def _with_stats(state: WorldState, entity_id: str, **stats: int) -> WorldState:
    entity = state.entity(entity_id)
    assert entity.actor is not None
    actor = dataclasses.replace(entity.actor, base_stats=tuple(sorted(stats.items())))
    return state.with_entity(dataclasses.replace(entity, actor=actor))


def _with_hp(state: WorldState, entity_id: str, hp: int) -> WorldState:
    entity = state.entity(entity_id)
    assert entity.actor is not None
    actor = dataclasses.replace(entity.actor, hp=hp)
    return state.with_entity(dataclasses.replace(entity, actor=actor))


@given(seed=st.integers(0, 2**32))
def test_a_strike_that_cannot_hit_misses(seed: int) -> None:
    state = _with_stats(_state(), "bandit-1", atk=0)
    state = _with_stats(state, PLAYER, **{"def": 30})
    events, _ = strike(state, "bandit-1", PLAYER, Rng.from_seed(seed))
    assert events == (AttackMissed(source="bandit-1", target=PLAYER),)


@given(seed=st.integers(0, 2**32))
def test_a_hit_does_at_least_1_and_at_most_atk_damage(seed: int) -> None:
    state = _with_hp(_with_stats(_state(), PLAYER, atk=12), "bandit-1", 99)
    events, _ = strike(state, PLAYER, "bandit-1", Rng.from_seed(seed))
    (damage,) = events
    assert isinstance(damage, DamageDealt)
    # The bandit has def 2, so 1 is taken off every roll but the lowest.
    assert 1 <= damage.amount <= 12 - 1


def test_lethal_damage_kills_a_foe_after_the_damage() -> None:
    state = _with_hp(_with_stats(_state(), PLAYER, atk=30), "bandit-1", 1)
    events, _ = strike(state, PLAYER, "bandit-1", Rng.from_seed(1))
    assert [type(event) for event in events] == [DamageDealt, ActorDied]


def test_lethal_damage_defeats_the_player_instead() -> None:
    state = _with_hp(_with_stats(_state(), "bandit-1", atk=30), PLAYER, 1)
    events, _ = strike(state, "bandit-1", PLAYER, Rng.from_seed(1))
    assert events[1:] == (Defeated(actor=PLAYER),)


def test_a_strike_draws_from_the_rng() -> None:
    rng = Rng.from_seed(1)
    _, after = strike(_state(), PLAYER, "bandit-1", rng)
    assert after != rng


def test_initiative_sorts_by_roll_plus_speed_and_breaks_ties_by_id() -> None:
    state = _with_stats(_state(), "bandit-1", spd=100)
    state = _with_stats(state, "goblin-1", spd=100)
    order, _ = roll_initiative(
        state, ("goblin-1", PLAYER, "bandit-1"), Rng.from_seed(3)
    )
    assert order[-1] == PLAYER
    # Equal speed, so the rolls decide; the same seed always decides the same.
    again, _ = roll_initiative(
        state, ("bandit-1", PLAYER, "goblin-1"), Rng.from_seed(3)
    )
    assert order == again


def test_melee_reach_is_one_step_in_the_same_area() -> None:
    state = _state()
    home = PosId.parse("village:1,1")
    assert melee_adjacent(state, home, PosId.parse("village:2,1"))
    assert not melee_adjacent(state, home, PosId.parse("village:2,2"))
    assert not melee_adjacent(state, home, PosId.parse("warren:1,1"))


def test_hostiles_are_listed_in_id_order() -> None:
    assert [entity.id for entity in hostile_actors(_state())] == [
        "bandit-1",
        "goblin-1",
        "hexer-1",
        "marauder-1",
    ]
