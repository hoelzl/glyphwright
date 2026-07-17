"""The lockpicking minigame: any mode with its own vocabulary and frame shape
inherits the whole kernel for free (design 0003 §10.3)."""

from __future__ import annotations

from glyphwright.api import Engine
from glyphwright.content.pack import reference_pack
from glyphwright.frames.frame import LockView
from glyphwright.kernel.commands import Abort, Move, Open, Pick, Take
from glyphwright.kernel.events import (
    ItemAcquired,
    MinigameResolved,
    ModePopped,
    ModePushed,
    PinSet,
    PinSlipped,
)
from glyphwright.kernel.state import PLAYER, fold


def _engine() -> Engine:
    return Engine.new(reference_pack(), seed=29)


def _at_chest() -> Engine:
    """Walk to the inn cellar, where the strongbox sits."""
    engine = _engine()
    for _ in range(6):
        engine.step(Move("east"))
    engine.step(Move("enter"))
    engine.step(Move("down"))
    return engine


def _with_key() -> Engine:
    engine = _at_chest()
    engine.step(Take("rusty-key"))
    return engine


def _picking() -> Engine:
    engine = _at_chest()
    engine.step(Open("strongbox"))
    return engine


# -- opening ------------------------------------------------------------------


def test_open_is_advertised_at_the_chest() -> None:
    engine = _engine()
    assert "open" not in engine.frame().commands.verb_names()
    engine = _at_chest()
    assert engine.frame().commands.domains("open") == (("strongbox",),)


def test_the_key_opens_the_chest_without_a_minigame() -> None:
    engine = _with_key()
    result = engine.step(Open("strongbox"))
    assert result.accepted
    assert not any(isinstance(e, ModePushed) for e in result.events)
    assert any(
        isinstance(e, ItemAcquired) and e.item == "silver-locket" for e in result.events
    )
    inventory = engine._state.entity(PLAYER).inventory
    assert inventory is not None and "silver-locket" in inventory.items
    assert engine._state.flags.get("opened:strongbox") is True


def test_an_open_chest_leaves_the_grammar() -> None:
    engine = _with_key()
    engine.step(Open("strongbox"))
    assert "open" not in engine.frame().commands.verb_names()


def test_opening_without_the_key_pushes_the_minigame() -> None:
    engine = _at_chest()
    result = engine.step(Open("strongbox"))
    pushes = [e for e in result.events if isinstance(e, ModePushed)]
    assert pushes and pushes[0].mode == "minigame:lockpick"
    assert engine._state.mode == "minigame:lockpick"
    assert engine._state.focus == ("strongbox", "0")


# -- picking ------------------------------------------------------------------


def test_lock_frames_show_the_pins() -> None:
    engine = _picking()
    frame = engine.frame()
    assert isinstance(frame.viewport, LockView)
    assert frame.viewport.target == "strongbox"
    assert (frame.viewport.pins, frame.viewport.total) == (0, 3)
    assert set(frame.commands.verb_names()) == {"pick", "abort", "look"}


def test_picks_click_or_slip_until_the_lock_opens() -> None:
    engine = _picking()
    for _ in range(60):
        if engine._state.mode != "minigame:lockpick":
            break
        result = engine.step(Pick())
        assert any(isinstance(e, (PinSet, PinSlipped)) for e in result.events), (
            "every pick must produce evidence"
        )
    assert engine._state.mode == "exploration"
    inventory = engine._state.entity(PLAYER).inventory
    assert inventory is not None and "silver-locket" in inventory.items


def test_success_emits_minigame_resolved_then_pops() -> None:
    engine = _picking()
    for _ in range(60):
        result = engine.step(Pick())
        resolved = [e for e in result.events if isinstance(e, MinigameResolved)]
        if resolved:
            assert resolved[0].minigame == "lockpick"
            assert resolved[0].outcome == "opened"
            kinds = [type(e) for e in result.events]
            assert kinds.index(MinigameResolved) < kinds.index(ModePopped)
            return
    raise AssertionError("the lock never opened in sixty attempts")


def test_a_slip_resets_progress() -> None:
    engine = _picking()
    for _ in range(60):
        result = engine.step(Pick())
        if any(isinstance(e, PinSlipped) for e in result.events):
            assert engine._state.focus == ("strongbox", "0")
            return
        if engine._state.mode != "minigame:lockpick":
            engine = _picking()  # opened without a single slip; try again
    raise AssertionError("sixty picks without one slip is not plausible")


def test_abort_leaves_the_lock_closed() -> None:
    engine = _picking()
    result = engine.step(Abort())
    pops = [e for e in result.events if isinstance(e, ModePopped)]
    assert pops and pops[0].outcome == "abandoned"
    assert engine._state.mode == "exploration"
    assert engine._state.focus is None
    assert not engine._state.flags.get("opened:strongbox")
    # The chest is still there to try again.
    assert "open" in engine.frame().commands.verb_names()


# -- determinism --------------------------------------------------------------


def test_lockpicking_folds_and_replays() -> None:
    engine = _picking()
    before = engine._state
    result = engine.step(Pick())
    assert fold(before, result.events) == engine._state

    def run() -> list[object]:
        e = Engine.new(reference_pack(), seed=37)
        for _ in range(6):
            e.step(Move("east"))
        e.step(Move("enter"))
        e.step(Move("down"))
        e.step(Open("strongbox"))
        return [e.step(Pick()).events for _ in range(10)]

    assert run() == run()


def test_the_rng_cursor_lands_in_state_per_pick() -> None:
    engine = _picking()
    before = engine._state.rng
    engine.step(Pick())
    assert engine._state.rng != before


# -- adversarial review regressions -------------------------------------------


def test_an_openable_with_unknown_contents_fails_at_load() -> None:
    import pytest

    from glyphwright.content.pack import ContentPack
    from glyphwright.world.entities import Actor, Entity, Openable, Position
    from glyphwright.world.grid import GridSpace

    space = GridSpace.from_text("here", "..")
    player = Entity(
        id="player",
        position=Position(at=space.pos(0, 0)),
        actor=Actor(name="P", hp=1, max_hp=1),
    )
    chest = Entity(
        id="chest",
        position=Position(at=space.pos(1, 0)),
        openable=Openable(contains="no-such-loot"),
    )
    with pytest.raises(ValueError, match="unknown entity"):
        ContentPack(name="broken", areas=(space,), entities=(player, chest))


def test_an_openable_with_an_unknown_key_fails_at_load() -> None:
    import pytest

    from glyphwright.content.pack import ContentPack
    from glyphwright.world.entities import Actor, Entity, Item, Openable, Position
    from glyphwright.world.grid import GridSpace

    space = GridSpace.from_text("here", "..")
    player = Entity(
        id="player",
        position=Position(at=space.pos(0, 0)),
        actor=Actor(name="P", hp=1, max_hp=1),
    )
    loot = Entity(id="loot", item=Item(name="Loot"))
    chest = Entity(
        id="chest",
        position=Position(at=space.pos(1, 0)),
        openable=Openable(contains="loot", key="no-such-key"),
    )
    with pytest.raises(ValueError, match="unknown key"):
        ContentPack(name="broken", areas=(space,), entities=(player, chest, loot))


def test_the_strongbox_is_visible_in_the_cellar() -> None:
    from glyphwright.frames.frame import RoomView

    engine = _at_chest()
    viewport = engine.frame().viewport
    assert isinstance(viewport, RoomView)
    assert "strongbox" in viewport.contents


def test_the_key_path_leaves_evidence() -> None:
    from glyphwright.kernel.events import ItemUsed

    engine = _with_key()
    result = engine.step(Open("strongbox"))
    used = [e for e in result.events if isinstance(e, ItemUsed)]
    assert used and used[0].item == "rusty-key" and not used[0].consumed
    assert "You use rusty-key." in result.frame.messages
    assert "rusty-key" in (engine._state.entity(PLAYER).inventory or ()).items  # type: ignore[union-attr]


def test_a_hostile_interrupts_the_lockpicking() -> None:
    """Picking a lock next to an awake hostile is not risk-free."""
    from glyphwright.kernel.events import AttackMissed, DamageDealt
    from glyphwright.world.entities import Actor, AiBehavior, Entity, Position
    from glyphwright.world.roomgraph import RoomGraphSpace

    engine = _at_chest()
    inn = engine._state.areas["inn"]
    assert isinstance(inn, RoomGraphSpace)
    rat = Entity(
        id="cellar-rat",
        position=Position(at=inn.pos("cellar")),
        actor=Actor(name="Rat", hp=4, max_hp=4, base_stats=(("atk", 1),)),
        ai=AiBehavior(hostile=True),
    )
    engine._state = engine._state.with_entity(rat)
    result = engine.step(Open("strongbox"))
    hostile_acts = [
        e
        for e in result.events
        if isinstance(e, (DamageDealt, AttackMissed)) and e.source == "cellar-rat"
    ]
    if not hostile_acts:
        result = engine.step(Pick())
        hostile_acts = [
            e
            for e in result.events
            if isinstance(e, (DamageDealt, AttackMissed)) and e.source == "cellar-rat"
        ]
    assert hostile_acts, "the world does not pause for a lock"


def test_defeat_mid_lockpick_collapses_to_the_defeated_grammar() -> None:
    import dataclasses

    from glyphwright.world.entities import Actor, AiBehavior, Entity, Position
    from glyphwright.world.roomgraph import RoomGraphSpace

    engine = _at_chest()
    inn = engine._state.areas["inn"]
    assert isinstance(inn, RoomGraphSpace)
    brute = Entity(
        id="cellar-brute",
        position=Position(at=inn.pos("cellar")),
        actor=Actor(name="Brute", hp=20, max_hp=20, base_stats=(("atk", 8),)),
        ai=AiBehavior(hostile=True),
    )
    engine._state = engine._state.with_entity(brute)
    player = engine._state.entity(PLAYER)
    assert player.actor is not None
    frail = dataclasses.replace(
        player,
        actor=dataclasses.replace(player.actor, hp=1, base_stats=(("def", 0),)),
    )
    engine._state = engine._state.with_entity(frail)
    engine.step(Open("strongbox"))
    for _ in range(30):
        if engine._state.flags.get("player-defeated"):
            break
        engine.step(Pick())
    assert engine._state.flags.get("player-defeated") is True
    assert engine._state.mode == "exploration", (
        "defeat must collapse the minigame to the defeated grammar"
    )
    assert engine.frame().commands.verb_names() == ("look",)
