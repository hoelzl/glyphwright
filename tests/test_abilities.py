"""Abilities, statuses, and effect primitives (design 0004, scoping 0003 §9)."""

from __future__ import annotations

import dataclasses

from glyphwright.api import Engine
from glyphwright.content.pack import reference_pack
from glyphwright.kernel.commands import Cast, Move, Wait
from glyphwright.kernel.events import (
    CastFizzled,
    DamageDealt,
    StatusApplied,
    StatusExpired,
)
from glyphwright.kernel.state import PLAYER, fold


def _engine() -> Engine:
    return Engine.new(reference_pack(), seed=43)


def _next_to_goblin() -> Engine:
    engine = _engine()
    engine.step(Move("east"))
    engine.step(Move("south"))
    return engine


# -- the grammar at arity two -------------------------------------------------


def test_cast_advertises_ability_and_target_domains() -> None:
    engine = _next_to_goblin()
    grammar = engine.frame().commands
    domains = grammar.domains("cast")
    assert len(domains) == 2, "cast is the first two-argument verb"
    assert "firebolt" in domains[0] and "guard" in domains[0]
    assert "goblin-1" in domains[1] and "player" in domains[1]


def test_self_abilities_alone_offer_only_the_caster() -> None:
    engine = _engine()  # nobody in reach at the start tile
    grammar = engine.frame().commands
    assert grammar.domains("cast") == (("guard",), ("player",))


def test_an_unqualified_ability_is_not_advertised() -> None:
    engine = _engine()
    player = engine._state.entity(PLAYER)
    assert player.actor is not None
    feeble = dataclasses.replace(
        player, actor=dataclasses.replace(player.actor, base_stats=(("atk", 1),))
    )
    engine._state = engine._state.with_entity(feeble)
    engine.step(Move("east"))
    engine.step(Move("south"))
    domains = engine.frame().commands.domains("cast")
    assert "firebolt" not in domains[0], "atk 1 does not meet firebolt's gate"


# -- casting ------------------------------------------------------------------


def test_firebolt_deals_ability_damage() -> None:
    engine = _next_to_goblin()
    result = engine.step(Cast("firebolt", "goblin-1"))
    assert result.accepted
    hits = [
        e
        for e in result.events
        if isinstance(e, DamageDealt) and e.target == "goblin-1"
    ]
    assert hits and hits[0].ability == "firebolt"
    assert 3 <= hits[0].amount <= 6  # amount 3 plus spread 0..3


def test_guard_applies_stoneskin_and_raises_def() -> None:
    from glyphwright.effects.stats import derive

    engine = _engine()
    base_def = derive(engine._state, PLAYER, "def").value
    result = engine.step(Cast("guard", "player"))
    assert result.accepted
    applied = [e for e in result.events if isinstance(e, StatusApplied)]
    assert applied and applied[0].status == "stoneskin"
    assert derive(engine._state, PLAYER, "def").value == base_def + 3
    derivation = derive(engine._state, PLAYER, "def")
    assert any("stoneskin" in c.source for c in derivation.contributions)


def test_statuses_appear_in_actor_summaries() -> None:
    engine = _engine()
    engine.step(Cast("guard", "player"))
    player = next(a for a in engine.frame().actors if a.id == PLAYER)
    assert "stoneskin" in player.statuses


def test_a_status_expires_on_schedule() -> None:
    engine = _engine()
    engine.step(Cast("guard", "player"))
    expired: list[StatusExpired] = []
    for _ in range(4):
        result = engine.step(Wait())
        expired.extend(e for e in result.events if isinstance(e, StatusExpired))
        if expired:
            break
    assert expired and expired[0].status == "stoneskin"
    from glyphwright.effects.stats import derive

    assert derive(engine._state, PLAYER, "def").value == 3, (
        "the bonus must fade with the status"
    )
    player = next(a for a in engine.frame().actors if a.id == PLAYER)
    assert player.statuses == ()


def test_reapplying_a_status_refreshes_its_clock() -> None:
    engine = _engine()
    engine.step(Cast("guard", "player"))
    engine.step(Wait())
    engine.step(Cast("guard", "player"))  # refresh
    result = engine.step(Wait())
    assert not any(isinstance(e, StatusExpired) for e in result.events), (
        "a refreshed status must not expire on the original clock"
    )
    player = next(a for a in engine.frame().actors if a.id == PLAYER)
    assert player.statuses.count("stoneskin") == 1, "no stacking, one instance"


# -- the cross-constraint refusal (design 0004 §2, 0003 A.5) ------------------


def test_a_mismatched_pairing_fizzles_as_a_world_refusal() -> None:
    engine = _next_to_goblin()
    before = engine.frame().turn
    result = engine.step(Cast("guard", "goblin-1"))
    assert result.accepted, "the grammar advertised both halves"
    fizzles = [e for e in result.events if isinstance(e, CastFizzled)]
    assert fizzles and fizzles[0].reason == "bad_target"
    assert engine.frame().turn == before + 1, "a refusal by the world costs the turn"
    assert not any(isinstance(e, StatusApplied) for e in result.events)


def test_an_unknown_ability_is_rejected_not_fizzled() -> None:
    engine = _engine()
    result = engine.step(Cast("meteor", "player"))
    assert result.rejection is not None
    assert result.rejection.reason == "cannot_cast"
    assert engine.frame().turn == 0


# -- battle -------------------------------------------------------------------


def test_cast_works_in_battle() -> None:
    engine = _engine()
    engine.step(Move("south"))  # the bandit engages
    assert engine._state.mode == "battle"
    grammar = engine.frame().commands
    assert "cast" in grammar.verb_names()
    assert "bandit-1" in grammar.domains("cast")[1]
    result = engine.step(Cast("firebolt", "bandit-1"))
    assert result.accepted
    assert any(
        isinstance(e, DamageDealt) and e.ability == "firebolt" for e in result.events
    )


# -- content validation -------------------------------------------------------


def test_an_ability_with_an_unknown_primitive_fails_at_load() -> None:
    import pytest

    from glyphwright.content.pack import ContentPack
    from glyphwright.effects.abilities import Ability
    from glyphwright.world.entities import Entity
    from glyphwright.world.grid import GridSpace

    space = GridSpace.from_text("here", "..")
    with pytest.raises(ValueError, match="unknown primitive"):
        ContentPack(
            name="broken",
            areas=(space,),
            entities=(Entity(id="e"),),
            abilities=(
                Ability(
                    id="oops",
                    name="Oops",
                    targeting="self",
                    effects=(("no_such_primitive", {}),),
                ),
            ),
        )


def test_an_actor_with_an_unknown_ability_fails_at_load() -> None:
    import pytest

    from glyphwright.content.pack import ContentPack
    from glyphwright.world.entities import Actor, Entity
    from glyphwright.world.grid import GridSpace

    space = GridSpace.from_text("here", "..")
    caster = Entity(
        id="e", actor=Actor(name="E", hp=1, max_hp=1, abilities=("no-such",))
    )
    with pytest.raises(ValueError, match="unknown ability"):
        ContentPack(name="broken", areas=(space,), entities=(caster,))


def test_apply_status_referencing_an_unknown_status_fails_at_load() -> None:
    import pytest

    from glyphwright.content.pack import ContentPack
    from glyphwright.effects.abilities import Ability
    from glyphwright.world.entities import Entity
    from glyphwright.world.grid import GridSpace

    space = GridSpace.from_text("here", "..")
    with pytest.raises(ValueError, match="unknown status"):
        ContentPack(
            name="broken",
            areas=(space,),
            entities=(Entity(id="e"),),
            abilities=(
                Ability(
                    id="hexed",
                    name="Hexed",
                    targeting="self",
                    effects=(("apply_status", {"status": "no-such", "duration": 1}),),
                ),
            ),
        )


# -- determinism --------------------------------------------------------------


def test_casts_fold_and_replay() -> None:
    engine = _next_to_goblin()
    before = engine._state
    result = engine.step(Cast("firebolt", "goblin-1"))
    assert fold(before, result.events) == engine._state

    def run() -> list[object]:
        e = Engine.new(reference_pack(), seed=53)
        e.step(Move("east"))
        e.step(Move("south"))
        e.step(Cast("guard", "player"))
        return [e.step(Cast("firebolt", "goblin-1")).events for _ in range(3)]

    assert run() == run()
