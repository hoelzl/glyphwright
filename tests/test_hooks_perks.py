"""Status hooks, perks, and AI ability use (design 0007, scoping 0003 §9.3)."""

from __future__ import annotations

import dataclasses
import pathlib
import tempfile
from collections.abc import Iterator

import pytest

from glyphwright.api import Engine
from glyphwright.content.loader import PackError, load_pack
from glyphwright.content.pack import ContentPack, reference_pack
from glyphwright.effects.stats import derive
from glyphwright.kernel.commands import Attack, Cast, Move, Wait
from glyphwright.kernel.events import (
    DamageDealt,
    ModePopped,
    PerkGained,
    StatusApplied,
    StatusExpired,
)
from glyphwright.kernel.state import PLAYER, fold


def _pack(files: dict[str, str]) -> ContentPack:
    with tempfile.TemporaryDirectory() as raw:
        root = pathlib.Path(raw)
        (root / "pack.toml").write_text('name = "hooks"\n', encoding="utf-8")
        for name, content in files.items():
            (root / name).write_text(content, encoding="utf-8")
        return load_pack(root)


_FIELD = '[[grid]]\narea = "field"\nrows = """\n.....\n"""\n'


def _venomed_player() -> Engine:
    """The reference player with venom folded on, three turns on the clock."""
    engine = Engine.new(reference_pack(), seed=5)
    engine._state = fold(
        engine._state,
        (StatusApplied(target=PLAYER, status="venom", expires=engine._state.turn + 3),),
    )
    return engine


# -- hooks: turn_end ----------------------------------------------------------


def test_a_turn_end_hook_ticks_in_the_event_log() -> None:
    engine = _venomed_player()
    before = engine._state.entity(PLAYER).actor
    assert before is not None
    result = engine.step(Wait())
    ticks = [
        e
        for e in result.events
        if isinstance(e, DamageDealt) and e.ability == "venom" and e.target == PLAYER
    ]
    assert len(ticks) == 1, "poison ticks once per closed turn"
    after = engine._state.entity(PLAYER).actor
    assert after is not None and after.hp < before.hp


def test_an_expired_status_stops_ticking() -> None:
    engine = _venomed_player()
    damage_steps = 0
    for _ in range(6):
        result = engine.step(Wait())
        if any(
            isinstance(e, DamageDealt) and e.ability == "venom" for e in result.events
        ):
            damage_steps += 1
        if any(isinstance(e, StatusExpired) for e in result.events):
            break
    after = engine.step(Wait())
    assert damage_steps > 0
    assert not any(
        isinstance(e, DamageDealt) and e.ability == "venom" for e in after.events
    ), "a faded status has no teeth"


def test_hooked_steps_fold_and_replay() -> None:
    engine = _venomed_player()
    before = engine._state
    result = engine.step(Wait())
    assert fold(before, result.events) == engine._state


# -- hooks: damage_taken and conditions ---------------------------------------


def _rage_pack(hp: int) -> ContentPack:
    return _pack(
        {
            "areas.toml": _FIELD,
            "entities.toml": (
                '[[entity]]\nid = "player"\nposition = "field:0,0"\n'
                "[entity.actor]\n"
                f"name = 'P'\nhp = {hp}\nmax_hp = 20\nperks = ['rage']\n"
                '[[entity]]\nid = "brute"\nposition = "field:1,0"\n'
                "[entity.actor]\nname = 'B'\nhp = 30\nmax_hp = 30\n"
                "stats = { atk = 4 }\n"
                "[entity.ai]\nhostile = true\n"
            ),
            "abilities.toml": (
                '[[status]]\nid = "rage"\nname = "Rage"\n'
                "hooks = [{ on = 'damage_taken', hp_below = 50, "
                "effects = [{ primitive = 'apply_status', status = 'hardened', "
                "duration = 2 }] }]\n"
                '[[status]]\nid = "hardened"\nname = "Hardened"\n'
                "modifiers = [{ stat = 'def', op = 'add', value = 3 }]\n"
            ),
        }
    )


def _struck_by_brute(engine: Engine) -> Iterator[tuple[object, ...]]:
    """Step until the brute lands a hit, yielding each step's events."""
    for _ in range(8):
        result = engine.step(Attack("brute"))
        yield result.events
        if any(
            isinstance(e, DamageDealt) and e.target == PLAYER for e in result.events
        ):
            return


def test_a_damage_taken_hook_fires_below_the_threshold() -> None:
    engine = Engine.new(_rage_pack(hp=8), seed=3)
    for _events in _struck_by_brute(engine):
        pass
    statuses = engine._state.entity(PLAYER).statuses
    assert statuses is not None and "hardened" in statuses.ids(), (
        "wounded below half, the rage perk hardens its bearer"
    )


def test_the_hook_holds_its_fire_above_the_threshold() -> None:
    engine = Engine.new(_rage_pack(hp=20), seed=3)
    for _events in _struck_by_brute(engine):
        pass
    actor = engine._state.entity(PLAYER).actor
    assert actor is not None and actor.hp * 100 >= actor.max_hp * 50
    statuses = engine._state.entity(PLAYER).statuses
    assert statuses is None or "hardened" not in statuses.ids()


def test_hook_events_trigger_no_further_hooks() -> None:
    """One generation per step: a self-harming damage_taken hook would cascade
    forever if its own damage re-triggered it (design 0007 §1)."""
    pack = _pack(
        {
            "areas.toml": _FIELD,
            "entities.toml": (
                '[[entity]]\nid = "player"\nposition = "field:0,0"\n'
                "[entity.actor]\nname = 'P'\nhp = 20\nmax_hp = 20\n"
                "perks = ['spite']\n"
                '[[entity]]\nid = "brute"\nposition = "field:1,0"\n'
                "[entity.actor]\nname = 'B'\nhp = 30\nmax_hp = 30\n"
                "stats = { atk = 4 }\n"
                "[entity.ai]\nhostile = true\n"
            ),
            "abilities.toml": (
                '[[status]]\nid = "spite"\nname = "Spite"\n'
                "hooks = [{ on = 'damage_taken', "
                "effects = [{ primitive = 'deal_damage', amount = 1 }] }]\n"
            ),
        }
    )
    engine = Engine.new(pack, seed=3)
    for events in _struck_by_brute(engine):
        last = events
    struck = [
        e
        for e in last
        if isinstance(e, DamageDealt) and e.target == PLAYER and e.ability != "spite"
    ]
    spite = [e for e in last if isinstance(e, DamageDealt) and e.ability == "spite"]
    assert len(spite) == len(struck), "each hit provokes exactly one spite tick"


# -- hooks end battles like anything else -------------------------------------


def test_a_poison_tick_can_end_a_battle() -> None:
    engine = Engine.new(reference_pack(), seed=11)
    engine.step(Move("south"))
    engine.step(Move("south"))  # the bandit engages a menu battle
    assert engine._state.mode == "battle"
    bandit = engine._state.entity("bandit-1")
    assert bandit.actor is not None
    dying = dataclasses.replace(bandit, actor=dataclasses.replace(bandit.actor, hp=1))
    engine._state = fold(
        engine._state.with_entity(dying),
        (
            StatusApplied(
                target="bandit-1", status="venom", expires=engine._state.turn + 3
            ),
        ),
    )
    # Wait is not a battle verb; a self-guard spends the turn without touching
    # the dying bandit, so only the poison can kill it.
    result = engine.step(Cast("guard", PLAYER))
    assert "bandit-1" not in engine._state.entities
    pops = [e for e in result.events if isinstance(e, ModePopped)]
    assert pops and pops[0].outcome == "victory", (
        "the tick lands before the outcome check, in the same step"
    )


# -- perks --------------------------------------------------------------------


def test_perks_join_the_stat_pipeline_with_provenance() -> None:
    engine = Engine.new(reference_pack(), seed=1)
    derivation = derive(engine._state, "marauder-1", "def")
    assert derivation.value == 4, "base 2, +2 grit"
    assert any(c.source == "grit (perk)" for c in derivation.contributions)


def test_grant_perk_is_an_event_and_regaining_is_idempotent() -> None:
    pack = _pack(
        {
            "areas.toml": _FIELD,
            "entities.toml": (
                '[[entity]]\nid = "player"\nposition = "field:0,0"\n'
                "[entity.actor]\nname = 'P'\nhp = 20\nmax_hp = 20\n"
                "abilities = ['ascend']\n"
            ),
            "abilities.toml": (
                '[[ability]]\nid = "ascend"\nname = "Ascend"\ntargeting = "self"\n'
                "effects = [{ primitive = 'grant_perk', perk = 'grit' }]\n"
                '[[status]]\nid = "grit"\nname = "Grit"\n'
                "modifiers = [{ stat = 'def', op = 'add', value = 2 }]\n"
            ),
        }
    )
    engine = Engine.new(pack, seed=1)
    base_def = derive(engine._state, PLAYER, "def").value
    result = engine.step(Cast("ascend", PLAYER))
    assert any(isinstance(e, PerkGained) for e in result.events)
    assert derive(engine._state, PLAYER, "def").value == base_def + 2
    engine.step(Cast("ascend", PLAYER))
    actor = engine._state.entity(PLAYER).actor
    assert actor is not None and actor.perks.count("grit") == 1


# -- AI ability use -----------------------------------------------------------


def _caster_pack() -> ContentPack:
    return _pack(
        {
            "areas.toml": _FIELD,
            "entities.toml": (
                '[[entity]]\nid = "player"\nposition = "field:0,0"\n'
                "[entity.actor]\nname = 'P'\nhp = 20\nmax_hp = 20\n"
                "stats = { atk = 3 }\n"
                '[[entity]]\nid = "warlock"\nposition = "field:3,0"\n'
                "[entity.actor]\nname = 'W'\nhp = 30\nmax_hp = 30\n"
                "stats = { atk = 2 }\nabilities = ['bolt']\n"
                "[entity.ai]\nhostile = true\n"
            ),
            "abilities.toml": (
                '[[ability]]\nid = "bolt"\nname = "Bolt"\ntargeting = "foe"\n'
                "effects = [{ primitive = 'deal_damage', amount = 2 }]\n"
            ),
        }
    )


def test_a_hostile_casts_when_it_cannot_strike() -> None:
    engine = Engine.new(_caster_pack(), seed=7)
    engine.step(Move("east"))
    engine.step(Move("east"))  # adjacent: the warlock strikes and wakes
    result = engine.step(Move("west"))  # out of reach: steel yields to magic
    casts = [
        e
        for e in result.events
        if isinstance(e, DamageDealt) and e.source == "warlock" and e.ability == "bolt"
    ]
    assert casts, "at range, a caster casts instead of closing"
    before = engine._state
    replayed = engine.step(Wait())
    assert fold(before, replayed.events) == engine._state


def test_a_cast_at_range_lands_its_status_too() -> None:
    """AI casting and hooks compose: an AI rockshard-style cast applies venom,
    and the venom ticks on the victim's own clock."""
    pack = _pack(
        {
            "areas.toml": _FIELD,
            "entities.toml": (
                '[[entity]]\nid = "player"\nposition = "field:0,0"\n'
                "[entity.actor]\nname = 'P'\nhp = 20\nmax_hp = 20\n"
                "stats = { atk = 3 }\n"
                '[[entity]]\nid = "warlock"\nposition = "field:3,0"\n'
                "[entity.actor]\nname = 'W'\nhp = 30\nmax_hp = 30\n"
                "stats = { atk = 2 }\nabilities = ['sting']\n"
                "[entity.ai]\nhostile = true\n"
            ),
            "abilities.toml": (
                '[[ability]]\nid = "sting"\nname = "Sting"\ntargeting = "foe"\n'
                "effects = [\n"
                "    { primitive = 'deal_damage', amount = 1 },\n"
                "    { primitive = 'apply_status', status = 'venom', duration = 2 },\n"
                "]\n"
                '[[status]]\nid = "venom"\nname = "Venom"\n'
                "hooks = [{ on = 'turn_end', "
                "effects = [{ primitive = 'deal_damage', amount = 1 }] }]\n"
            ),
        }
    )
    engine = Engine.new(pack, seed=7)
    engine.step(Move("east"))
    engine.step(Move("east"))
    result = engine.step(Move("west"))
    assert any(
        isinstance(e, StatusApplied) and e.target == PLAYER and e.status == "venom"
        for e in result.events
    ), "the AI's cast runs its whole effect chain"
    assert not any(
        isinstance(e, DamageDealt) and e.ability == "venom" for e in result.events
    ), "a status applied mid-round does not tick retroactively in the same step"
    # Silence the warlock so it cannot refresh the clock, then count ticks:
    # the AI-applied duration-2 venom covers exactly two of the player's
    # turns, the same coverage a player cast would set.
    from glyphwright.kernel.events import ActorDied

    engine._state = fold(engine._state, (ActorDied(actor="warlock"),))
    tick_steps = 0
    for _ in range(5):
        later = engine.step(Wait())
        if any(
            isinstance(e, DamageDealt) and e.ability == "venom" for e in later.events
        ):
            tick_steps += 1
    assert tick_steps == 2, "durations mean the same thing for every caster"


# -- validation ---------------------------------------------------------------


def test_an_unknown_hook_trigger_is_a_load_error() -> None:
    with pytest.raises(PackError, match="trigger"):
        _pack(
            {
                "areas.toml": _FIELD,
                "entities.toml": (
                    '[[entity]]\nid = "player"\nposition = "field:0,0"\n'
                    "[entity.actor]\nname = 'P'\nhp = 5\nmax_hp = 5\n"
                ),
                "abilities.toml": (
                    '[[status]]\nid = "odd"\nname = "Odd"\n'
                    "hooks = [{ on = 'sneeze', "
                    "effects = [{ primitive = 'heal', amount = 1 }] }]\n"
                ),
            }
        )


def test_an_out_of_range_hp_below_is_a_load_error() -> None:
    with pytest.raises(PackError, match="hp_below"):
        _pack(
            {
                "areas.toml": _FIELD,
                "entities.toml": (
                    '[[entity]]\nid = "player"\nposition = "field:0,0"\n'
                    "[entity.actor]\nname = 'P'\nhp = 5\nmax_hp = 5\n"
                ),
                "abilities.toml": (
                    '[[status]]\nid = "odd"\nname = "Odd"\n'
                    "hooks = [{ on = 'turn_end', hp_below = 0, "
                    "effects = [{ primitive = 'heal', amount = 1 }] }]\n"
                ),
            }
        )


def test_an_unknown_perk_on_an_actor_is_a_load_error() -> None:
    with pytest.raises(PackError, match="perk"):
        _pack(
            {
                "areas.toml": _FIELD,
                "entities.toml": (
                    '[[entity]]\nid = "player"\nposition = "field:0,0"\n'
                    "[entity.actor]\nname = 'P'\nhp = 5\nmax_hp = 5\n"
                    "perks = ['ghost']\n"
                ),
            }
        )


def test_granting_an_unknown_perk_is_a_load_error() -> None:
    with pytest.raises(PackError, match="perk"):
        _pack(
            {
                "areas.toml": _FIELD,
                "entities.toml": (
                    '[[entity]]\nid = "player"\nposition = "field:0,0"\n'
                    "[entity.actor]\nname = 'P'\nhp = 5\nmax_hp = 5\n"
                    "abilities = ['ascend']\n"
                ),
                "abilities.toml": (
                    '[[ability]]\nid = "ascend"\nname = "A"\ntargeting = "self"\n'
                    "effects = [{ primitive = 'grant_perk', perk = 'ghost' }]\n"
                ),
            }
        )


def test_a_caster_chases_across_areas_instead_of_bombarding() -> None:
    """The area gate on AI casting: a caster has ears but not artillery."""
    pack = _pack(
        {
            "areas.toml": (
                '[[grid]]\narea = "field"\nrows = """\n.....\n"""\n'
                '[[grid]]\narea = "refuge"\nrows = """\n...\n"""\n'
            ),
            "entities.toml": (
                '[[entity]]\nid = "player"\nposition = "field:0,0"\n'
                "[entity.actor]\nname = 'P'\nhp = 20\nmax_hp = 20\n"
                "stats = { atk = 3 }\n"
                '[[entity]]\nid = "warlock"\nposition = "field:2,0"\n'
                "[entity.actor]\nname = 'W'\nhp = 30\nmax_hp = 30\n"
                "stats = { atk = 2 }\nabilities = ['bolt']\n"
                "[entity.ai]\nhostile = true\n"
                '[[entity]]\nid = "hatch"\nposition = "field:0,0"\n'
                '[entity.portal]\ntoken = "down"\nto = "refuge:0,0"\n'
            ),
            "abilities.toml": (
                '[[ability]]\nid = "bolt"\nname = "Bolt"\ntargeting = "foe"\n'
                "effects = [{ primitive = 'deal_damage', amount = 2 }]\n"
            ),
        }
    )
    engine = Engine.new(pack, seed=7)
    engine.step(Move("east"))  # adjacent: struck and provoked
    result = engine.step(Move("west"))  # back onto the hatch: casts (same area)
    assert any(
        isinstance(e, DamageDealt) and e.source == "warlock" for e in result.events
    )
    fled = engine.step(Move("down"))  # another area entirely
    assert not any(
        isinstance(e, DamageDealt) and e.source == "warlock" for e in fled.events
    ), "no artillery across area boundaries"
    assert engine._state.mode == "exploration"


def test_perk_gained_validates_on_the_wire() -> None:
    from glyphwright.frontends.wire import encode_event
    from glyphwright.harness.schema import all_schemas

    schema = all_schemas()["glyphwright.event.v8.json"]
    payload = encode_event(PerkGained(target=PLAYER, perk="grit"), turn=3)
    assert payload["type"] in schema["properties"]["type"]["enum"], (
        "the schema's closed type enum must admit the event the bump added"
    )
    for key in payload:
        assert key in schema["properties"]
