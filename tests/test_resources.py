"""Resource pools and ability costs (design 0009, lifting 0004 §2's deferral)."""

from __future__ import annotations

import pathlib
import tempfile

import pytest

from glyphwright.api import Engine
from glyphwright.content.loader import PackError, load_pack
from glyphwright.content.pack import ContentPack, reference_pack
from glyphwright.kernel.commands import Cast, Move, Take, Use, Wait
from glyphwright.kernel.events import (
    CastFizzled,
    ManaRestored,
    ManaSpent,
    Moved,
)
from glyphwright.kernel.state import PLAYER, fold


def _mp(engine: Engine, entity_id: str = PLAYER) -> list[int]:
    value = engine.query(f"{entity_id}.mp").value
    assert isinstance(value, list)
    return value


def _pack(files: dict[str, str]) -> ContentPack:
    with tempfile.TemporaryDirectory() as raw:
        root = pathlib.Path(raw)
        (root / "pack.toml").write_text('name = "pools"\n', encoding="utf-8")
        for name, content in files.items():
            (root / name).write_text(content, encoding="utf-8")
        return load_pack(root)


# -- spending -----------------------------------------------------------------


def test_a_cast_spends_its_cost_in_the_event_log() -> None:
    engine = Engine.new(reference_pack(), seed=3)
    assert _mp(engine) == [8, 8]
    result = engine.step(Cast("guard", PLAYER))
    spends = [e for e in result.events if isinstance(e, ManaSpent)]
    assert spends == [ManaSpent(caster=PLAYER, amount=1)]
    assert _mp(engine) == [7, 8]


def test_spending_folds_and_replays() -> None:
    engine = Engine.new(reference_pack(), seed=3)
    before = engine._state
    result = engine.step(Cast("guard", PLAYER))
    assert fold(before, result.events) == engine._state


def test_an_unaffordable_ability_is_not_advertised() -> None:
    """Affordability is advertisement: the grammar stops offering what the
    caster cannot pay for, and the attempt is a typed rejection."""
    engine = Engine.new(reference_pack(), seed=3)
    for _ in range(8):  # 8 mp of guards at cost 1
        engine.step(Cast("guard", PLAYER))
    assert _mp(engine) == [0, 8]
    assert "cast" not in engine.frame().commands.verb_names(), (
        "an empty pool leaves nothing castable"
    )
    result = engine.step(Cast("guard", PLAYER))
    assert not result.accepted


def test_a_fizzle_spends_no_mana() -> None:
    """The cast never resolved; the turn is the fizzle's whole price."""
    engine = Engine.new(reference_pack(), seed=3)
    engine.step(Move("east"))
    engine.step(Move("south"))  # beside the goblin: it enters the cast domain
    mp_before = _mp(engine)
    result = engine.step(Cast("guard", "goblin-1"))
    assert any(isinstance(e, CastFizzled) for e in result.events), (
        "a self-ability aimed at a foe is a refusal by the world"
    )
    assert not any(isinstance(e, ManaSpent) for e in result.events)
    assert _mp(engine) == mp_before


# -- recovery -----------------------------------------------------------------


def test_a_tonic_restores_mana_post_clamp() -> None:
    engine = Engine.new(reference_pack(), seed=3)
    for command in (
        Move("east"),
        Move("east"),
        Move("east"),
        Move("east"),
        Move("south"),
        Move("south"),
    ):
        engine.step(command)
    result = engine.step(Take("tonic"))
    assert result.accepted, "the tonic lies at village:5,3"
    assert "use" not in engine.frame().commands.verb_names(), (
        "a full pool makes the tonic useless, so it is not offered"
    )
    engine.step(Cast("guard", PLAYER))
    engine.step(Cast("guard", PLAYER))
    engine.step(Cast("guard", PLAYER))
    assert _mp(engine) == [5, 8]
    result = engine.step(Use("tonic"))
    restored = [e for e in result.events if isinstance(e, ManaRestored)]
    assert restored and restored[0].amount == 3, (
        "events record what landed after the clamp, not the label on the bottle"
    )
    assert _mp(engine) == [8, 8]


# -- the AI runs dry ----------------------------------------------------------


def test_a_dry_caster_returns_to_the_chase() -> None:
    pack = _pack(
        {
            "areas.toml": '[[grid]]\narea = "field"\nrows = """\n......\n"""\n',
            "entities.toml": (
                '[[entity]]\nid = "player"\nposition = "field:0,0"\n'
                "[entity.actor]\nname = 'P'\nhp = 30\nmax_hp = 30\n"
                "stats = { atk = 3 }\n"
                '[[entity]]\nid = "warlock"\nposition = "field:3,0"\n'
                "[entity.actor]\nname = 'W'\nhp = 30\nmax_hp = 30\n"
                "mp = 2\nmax_mp = 2\n"
                "stats = { atk = 2 }\nabilities = ['bolt']\n"
                "[entity.ai]\nhostile = true\n"
            ),
            "abilities.toml": (
                '[[ability]]\nid = "bolt"\nname = "Bolt"\ntargeting = "foe"\n'
                "cost = 2\n"
                "effects = [{ primitive = 'deal_damage', amount = 1 }]\n"
            ),
        }
    )
    engine = Engine.new(pack, seed=7)
    engine.step(Move("east"))
    engine.step(Move("east"))  # adjacent: struck and provoked
    result = engine.step(Move("west"))  # at range: one bolt, the whole pool
    assert any(
        isinstance(e, ManaSpent) and e.caster == "warlock" for e in result.events
    )
    assert _mp(engine, "warlock") == [0, 2]
    chased = engine.step(Wait())
    assert any(isinstance(e, Moved) and e.actor == "warlock" for e in chased.events), (
        "dry, the turret goes back to being a pursuer"
    )
    assert not any(isinstance(e, ManaSpent) for e in chased.events)


# -- validation ---------------------------------------------------------------


def test_an_overfull_pool_is_a_load_error() -> None:
    with pytest.raises(PackError, match="mp"):
        _pack(
            {
                "areas.toml": '[[grid]]\narea = "field"\nrows = """\n...\n"""\n',
                "entities.toml": (
                    '[[entity]]\nid = "player"\nposition = "field:0,0"\n'
                    "[entity.actor]\nname = 'P'\nhp = 5\nmax_hp = 5\n"
                    "mp = 9\nmax_mp = 4\n"
                ),
            }
        )


def test_a_negative_cost_is_a_load_error() -> None:
    with pytest.raises(PackError, match="cost"):
        _pack(
            {
                "areas.toml": '[[grid]]\narea = "field"\nrows = """\n...\n"""\n',
                "entities.toml": (
                    '[[entity]]\nid = "player"\nposition = "field:0,0"\n'
                    "[entity.actor]\nname = 'P'\nhp = 5\nmax_hp = 5\n"
                ),
                "abilities.toml": (
                    '[[ability]]\nid = "gift"\nname = "Gift"\ntargeting = "self"\n'
                    "cost = -1\n"
                    "effects = [{ primitive = 'heal', amount = 1 }]\n"
                ),
            }
        )


def test_a_consumable_that_restores_nothing_is_a_load_error() -> None:
    with pytest.raises(PackError, match="nothing"):
        _pack(
            {
                "areas.toml": '[[grid]]\narea = "field"\nrows = """\n...\n"""\n',
                "entities.toml": (
                    '[[entity]]\nid = "player"\nposition = "field:0,0"\n'
                    "[entity.actor]\nname = 'P'\nhp = 5\nmax_hp = 5\n"
                    '[[entity]]\nid = "dud"\nposition = "field:2,0"\n'
                    "[entity.item]\nname = 'Dud'\n"
                    "[entity.consumable]\n"
                ),
            }
        )


# -- frames -------------------------------------------------------------------


def test_the_frame_reports_pools_only_where_they_exist() -> None:
    engine = Engine.new(reference_pack(), seed=3)
    actors = {actor.id: actor for actor in engine.frame().actors}
    assert actors[PLAYER].mp == (8, 8)
    assert actors["goblin-1"].mp is None, (
        "absence means no mana system, never an empty pool"
    )


def test_the_pool_survives_a_mode_change() -> None:
    """The mana pool must not vanish mid-session: a dialogue frame reports
    it exactly like exploration and battle (one summary factory)."""
    from glyphwright.kernel.commands import Talk

    engine = Engine.new(reference_pack(), seed=3)
    for _ in range(6):
        engine.step(Move("east"))
    engine.step(Move("enter"))
    grammar = engine.frame().commands
    assert "talk" in grammar.verb_names(), "the inn holds a speaker"
    speaker = grammar.domains("talk")[0][0]
    engine.step(Talk(speaker))
    assert engine._state.mode == "dialogue"
    player = next(a for a in engine.frame().actors if a.id == PLAYER)
    assert player.mp == (8, 8), "the pool does not vanish mid-conversation"


def test_a_dual_elixir_never_records_a_zero_restoration() -> None:
    """Events are evidence of what landed: a dual consumable used at full hp
    emits no Healed(0)."""
    from glyphwright.kernel.events import Healed

    pack = _pack(
        {
            "areas.toml": '[[grid]]\narea = "field"\nrows = """\n...\n"""\n',
            "entities.toml": (
                '[[entity]]\nid = "player"\nposition = "field:0,0"\n'
                "[entity.actor]\nname = 'P'\nhp = 10\nmax_hp = 10\n"
                "mp = 1\nmax_mp = 6\n"
                '[[entity]]\nid = "elixir"\nposition = "field:1,0"\n'
                "[entity.item]\nname = 'Elixir'\n"
                "[entity.consumable]\nheal = 5\nmana = 5\n"
            ),
        }
    )
    engine = Engine.new(pack, seed=1)
    engine.step(Move("east"))
    engine.step(Take("elixir"))
    result = engine.step(Use("elixir"))
    assert result.accepted
    assert not any(isinstance(e, Healed) for e in result.events), (
        "full hp: no Healed event at all, never a zero-amount one"
    )
    restored = [e for e in result.events if isinstance(e, ManaRestored)]
    assert restored and restored[0].amount == 5
