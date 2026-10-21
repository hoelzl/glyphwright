"""Combat and mode-stack events: their fold, their messages, their wire form."""

from __future__ import annotations

from typing import get_args

import pytest
from jsonschema import Draft202012Validator

from glyphwright.api import reference_pack
from glyphwright.frontends.wire import encode_event
from glyphwright.harness.schema import event_schema
from glyphwright.kernel.events import (
    ActorDied,
    AttackMissed,
    DamageDealt,
    Defeated,
    Event,
    FleeFailed,
    Healed,
    ItemAcquired,
    ItemEquipped,
    ItemUsed,
    ModePopped,
    ModePushed,
    MoveBlocked,
    Moved,
    Provoked,
    TurnAdvanced,
)
from glyphwright.kernel.state import (
    MODE_BATTLE,
    MODE_EXPLORATION,
    PLAYER,
    WorldState,
    apply,
    fold,
)
from glyphwright.modes.messages import describe
from glyphwright.world.space import PosId

HOME = PosId.parse("village:1,1")
NEXT = PosId.parse("village:2,1")
BATTLE = ModePushed(mode=MODE_BATTLE, initiative=("bandit-1", "goblin-1"))

# One instance of every event type, for the wire checks below.
SAMPLES: tuple[Event, ...] = (
    Moved(actor=PLAYER, origin=HOME, destination=NEXT, exit="east"),
    MoveBlocked(actor=PLAYER, origin=HOME, exit="north", reason="wall"),
    TurnAdvanced(turn=1, rng="pcg64:1"),
    ItemAcquired(actor=PLAYER, item="potion-minor", origin=NEXT),
    ItemUsed(actor=PLAYER, item="potion-minor", target=PLAYER),
    ItemEquipped(actor=PLAYER, item="iron-sword", slot="weapon"),
    Healed(target=PLAYER, amount=3, source="potion-minor"),
    Provoked(actor="bandit-1"),
    DamageDealt(source=PLAYER, target="bandit-1", amount=4),
    AttackMissed(source="bandit-1", target=PLAYER),
    ActorDied(actor="bandit-1"),
    Defeated(actor=PLAYER),
    BATTLE,
    ModePopped(mode=MODE_BATTLE, outcome="victory"),
    FleeFailed(actor=PLAYER),
)


def _state() -> WorldState:
    from glyphwright.api import Engine

    return Engine.new(reference_pack(), seed=1)._state


def _hp(state: WorldState, entity_id: str) -> int:
    actor = state.entity(entity_id).actor
    assert actor is not None
    return actor.hp


def test_every_event_type_has_a_sample() -> None:
    assert {type(sample) for sample in SAMPLES} == set(get_args(Event))


@pytest.mark.parametrize("event", SAMPLES, ids=lambda event: event.type)
def test_every_event_validates_on_the_wire(event: Event) -> None:
    Draft202012Validator(event_schema()).validate(encode_event(event, turn=1))


def test_provoked_wakes_the_hostile() -> None:
    state = apply(_state(), Provoked(actor="bandit-1"))
    ai = state.entity("bandit-1").ai
    assert ai is not None and ai.aggroed


def test_damage_clamps_hp_at_zero() -> None:
    state = apply(_state(), DamageDealt(source=PLAYER, target="bandit-1", amount=99))
    assert _hp(state, "bandit-1") == 0


def test_the_dead_leave_the_world_and_the_initiative() -> None:
    state = fold(_state(), (BATTLE, ActorDied(actor="bandit-1")))
    assert "bandit-1" not in state.entities
    assert state.initiative == ("goblin-1",)


def test_the_player_is_defeated_not_removed() -> None:
    state = _state()
    with pytest.raises(ValueError, match="never removed"):
        apply(state, ActorDied(actor=PLAYER))
    assert not state.defeated
    beaten = apply(state, DamageDealt(source="bandit-1", target=PLAYER, amount=99))
    assert beaten.defeated and PLAYER in beaten.entities


def test_push_and_pop_move_the_mode_stack_and_the_initiative() -> None:
    pushed = apply(_state(), BATTLE)
    assert pushed.mode_stack == (MODE_EXPLORATION, MODE_BATTLE)
    assert pushed.initiative == ("bandit-1", "goblin-1")
    popped = apply(pushed, ModePopped(mode=MODE_BATTLE, outcome="fled"))
    assert popped.mode_stack == (MODE_EXPLORATION,)
    assert popped.initiative == ()


def test_popping_a_mode_that_is_not_active_is_an_error() -> None:
    with pytest.raises(ValueError, match="cannot pop 'battle'"):
        apply(_state(), ModePopped(mode=MODE_BATTLE, outcome="victory"))


def test_defeat_is_announced_once() -> None:
    # v2 finding N14: v0 said both "You are defeated." and "You have fallen.".
    said = [
        describe(event)
        for event in (
            Defeated(actor=PLAYER),
            ModePopped(mode=MODE_BATTLE, outcome="defeat"),
        )
    ]
    assert [message for message in said if message] == ["You are defeated."]
