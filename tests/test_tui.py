"""The TUI: keystrokes translate to the one command language, and painting is
a pure function of the frame (design 0003 sections 6, 12, ADR-003)."""

from __future__ import annotations

import io

from glyphwright.api import Engine
from glyphwright.content.pack import reference_pack
from glyphwright.frontends.tui import keys, render, session
from glyphwright.kernel.commands import Attack, Flee, Look, Move, Take, Wait


def _engine() -> Engine:
    return Engine.new(reference_pack(), seed=17)


# -- key translation ----------------------------------------------------------


def test_arrows_and_vi_keys_translate_to_moves() -> None:
    engine = _engine()
    frame = engine.frame()
    for key, token in (
        ("UP", "north"),
        ("DOWN", "south"),
        ("LEFT", "west"),
        ("RIGHT", "east"),
        ("k", "north"),
        ("j", "south"),
        ("h", "west"),
        ("l", "east"),
    ):
        assert keys.translate(key, frame) == Move(token)


def test_hotkeys_take_the_first_advertised_referent() -> None:
    engine = _engine()
    engine.step(Move("east"))
    engine.step(Move("east"))  # standing on the potion
    frame = engine.frame()
    assert keys.translate("t", frame) == Take("potion-minor")


def test_wait_and_look_keys() -> None:
    frame = _engine().frame()
    assert keys.translate(".", frame) == Wait()
    assert keys.translate(" ", frame) == Wait()
    assert keys.translate("x", frame) == Look()


def test_attack_key_targets_the_first_foe() -> None:
    engine = _engine()
    engine.step(Move("east"))
    engine.step(Move("south"))  # adjacent to the goblin
    frame = engine.frame()
    assert keys.translate("a", frame) == Attack("goblin-1")


def test_flee_key_in_battle() -> None:
    engine = _engine()
    engine.step(Move("south"))  # bandit engages
    assert engine._state.mode == "battle"
    frame = engine.frame()
    assert keys.translate("f", frame) == Flee()
    assert keys.translate("u", frame) is None  # nothing usable is carried


def test_unadvertised_hotkeys_translate_to_nothing() -> None:
    frame = _engine().frame()
    assert keys.translate("t", frame) is None
    assert keys.translate("f", frame) is None
    assert keys.translate("Z", frame) is None


def test_number_keys_pick_exits_in_listed_order() -> None:
    engine = _engine()
    for _ in range(6):
        engine.step(Move("east"))  # at the inn door: east, enter, south, west
    frame = engine.frame()
    domain = frame.commands.domains("move")[0]
    assert keys.translate("1", frame) == Move(domain[0])
    assert keys.translate("2", frame) == Move(domain[1])
    assert keys.translate("9", frame) is None


# -- painting is a pure function of the frame ---------------------------------


def test_paint_is_pure_and_deterministic() -> None:
    engine = _engine()
    frame = engine.frame()
    log = ("You wake.",)
    assert render.paint(frame, log) == render.paint(frame, log)


def test_paint_shows_map_status_and_log() -> None:
    engine = _engine()
    engine.step(Move("east"))
    frame = engine.frame()
    screen = render.paint(frame, ("You go east.",))
    assert "#########" in screen
    assert "hp 17/20" in screen
    assert "You go east." in screen
    assert "village" in screen


def test_paint_renders_room_frames_as_prose() -> None:
    engine = _engine()
    for _ in range(6):
        engine.step(Move("east"))
    engine.step(Move("enter"))
    screen = render.paint(engine.frame(), ())
    assert "The Gilded Tankard" in screen
    assert "1) down" in screen or "1) out" in screen


def test_paint_renders_battle_frames_with_combatants() -> None:
    engine = _engine()
    engine.step(Move("south"))
    assert engine._state.mode == "battle"
    screen = render.paint(engine.frame(), ())
    assert "battle" in screen
    assert "bandit-1" in screen


def test_paint_starts_with_a_full_clear() -> None:
    engine = _engine()
    screen = render.paint(engine.frame(), ())
    assert screen.startswith("\x1b[2J\x1b[H")


# -- the session loop over scripted keys --------------------------------------


def test_a_scripted_session_plays_and_quits() -> None:
    engine = _engine()
    output = io.StringIO()
    code = session.run_session(
        engine, iter(["l", "l", ".", "q"]), output, harness=False
    )
    assert code == 0
    assert engine.frame().turn == 3
    assert "\x1b[?1049h" in output.getvalue(), "must enter the alternate screen"
    assert output.getvalue().rstrip().endswith("\x1b[?1049l"), (
        "must restore the terminal on the way out"
    )


def test_the_command_bar_accepts_typed_commands() -> None:
    engine = _engine()
    output = io.StringIO()
    session.run_session(
        engine,
        iter([*";move east\r", "q"]),
        output,
        harness=False,
    )
    at = engine._state.entity("player").at()
    assert at is not None and at.local == "2,1"


def test_the_meta_bar_needs_harness() -> None:
    engine = _engine()
    output = io.StringIO()
    session.run_session(engine, iter([*":seed\r", "q"]), output, harness=True)
    assert "seed = 17" in output.getvalue()


def test_rejections_are_surfaced_in_the_log() -> None:
    engine = _engine()
    output = io.StringIO()
    session.run_session(engine, iter(["k", "q"]), output, harness=False)
    # north from (1,1) is a wall: a valid move the world refuses, in prose.
    assert "wall blocks" in output.getvalue()
