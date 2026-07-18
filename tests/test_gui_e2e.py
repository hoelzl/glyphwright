"""The GUI's pygame side, headless: painting real surfaces and driving the
real event pump under SDL's dummy video driver (design 0011 §5.4).

These tests need the ``gui`` extra and skip cleanly without it — the bare CI
job proves everything else survives its absence.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator

import pytest

# The driver must be chosen before display.init; setdefault keeps a
# deliberately different local configuration working.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

pytest.importorskip("pygame")

import pygame  # noqa: E402

from glyphwright.api import Engine  # noqa: E402
from glyphwright.content.pack import reference_pack  # noqa: E402
from glyphwright.frames.frame import SemanticFrame  # noqa: E402
from glyphwright.frontends.gui import paint, scene, session  # noqa: E402
from glyphwright.kernel.commands import Move  # noqa: E402

pytestmark = pytest.mark.e2e


def _engine() -> Engine:
    return Engine.new(reference_pack(), seed=17)


@pytest.fixture
def surface() -> Iterator[pygame.Surface]:
    pygame.display.init()
    pygame.font.init()
    yield pygame.display.set_mode(paint.WINDOW_SIZE)
    pygame.display.quit()


def _hash(surface: pygame.Surface) -> str:
    return hashlib.sha256(pygame.image.tobytes(surface, "RGB")).hexdigest()


def _representative_frames() -> list[SemanticFrame]:
    engine = _engine()
    frames = [engine.frame()]
    frames.append(engine.step(Move("east")).frame)  # a grid frame with messages
    engine = _engine()
    engine.step(Move("south"))
    frames.append(engine.frame())  # a battle frame
    engine = _engine()
    for _ in range(6):
        engine.step(Move("east"))
    frames.append(engine.step(Move("enter")).frame)  # a room frame
    return frames


def test_every_representative_scene_paints(surface: pygame.Surface) -> None:
    for frame in _representative_frames():
        paint.paint(scene.compose(frame, frame.messages), surface)


def test_painting_is_deterministic_within_a_process(
    surface: pygame.Surface,
) -> None:
    frame = _engine().step(Move("east")).frame
    composed = scene.compose(frame, frame.messages)
    paint.paint(composed, surface)
    first = _hash(surface)
    paint.paint(composed, surface)
    assert _hash(surface) == first


def test_distinct_scenes_paint_distinct_pixels(surface: pygame.Surface) -> None:
    engine = _engine()
    composed = scene.compose(engine.frame(), ())
    paint.paint(composed, surface)
    before = _hash(surface)
    frame = engine.step(Move("east")).frame
    paint.paint(scene.compose(frame, frame.messages), surface)
    assert _hash(surface) != before


def _post_keys(*keys: tuple[int, str]) -> None:
    for key, unicode in keys:
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, unicode=unicode))


def test_a_scripted_session_plays_and_quits() -> None:
    engine = _engine()
    pygame.display.init()
    try:
        _post_keys(
            (pygame.K_RIGHT, ""),  # move east
            (pygame.K_PERIOD, "."),  # wait
            (pygame.K_F1, ""),  # meaningless key: must be ignored
            (pygame.K_q, "q"),  # quit
        )
        assert session.run_session(engine) == 0
    finally:
        pygame.display.quit()
    assert engine.frame().turn == 2


def test_closing_the_window_ends_the_session() -> None:
    engine = _engine()
    pygame.display.init()
    try:
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        assert session.run_session(engine) == 0
    finally:
        pygame.display.quit()
    assert engine.frame().turn == 0


def test_a_refused_move_keeps_the_session_running() -> None:
    engine = _engine()
    pygame.display.init()
    try:
        # north from the start is a wall: the world refuses in prose (0003
        # appendix A.5), the turn advances, and the session keeps running.
        _post_keys((pygame.K_UP, ""), (pygame.K_q, "q"))
        assert session.run_session(engine) == 0
    finally:
        pygame.display.quit()
    assert engine.frame().turn == 1


def _post_text(text: str) -> None:
    for char in text:
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=0, unicode=char))
    pygame.event.post(
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, unicode="\r")
    )


def test_the_command_bar_accepts_typed_commands() -> None:
    engine = _engine()
    pygame.display.init()
    try:
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=0, unicode=";"))
        _post_text("move east")
        _post_keys((pygame.K_q, "q"))
        assert session.run_session(engine) == 0
    finally:
        pygame.display.quit()
    assert engine.frame().turn == 1


def test_escape_cancels_the_bar_without_stepping() -> None:
    engine = _engine()
    pygame.display.init()
    try:
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=0, unicode=";"))
        pygame.event.post(
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, unicode="")
        )
        _post_keys((pygame.K_q, "q"))
        assert session.run_session(engine) == 0
    finally:
        pygame.display.quit()
    assert engine.frame().turn == 0


def test_closing_the_window_while_typing_still_quits() -> None:
    engine = _engine()
    pygame.display.init()
    try:
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=0, unicode=";"))
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        assert session.run_session(engine) == 0
    finally:
        pygame.display.quit()
    assert engine.frame().turn == 0


def test_the_meta_bar_is_gated_and_does_not_advance_the_turn() -> None:
    engine = _engine()
    pygame.display.init()
    try:
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=0, unicode=":"))
        _post_text("seed")
        _post_keys((pygame.K_q, "q"))
        assert session.run_session(engine, harness=True) == 0
    finally:
        pygame.display.quit()
    assert engine.frame().turn == 0


def test_a_battle_is_played_with_hotkeys() -> None:
    engine = _engine()
    pygame.display.init()
    try:
        # South engages the bandit; 'a' strikes it once; 'f' breaks contact.
        _post_keys(
            (pygame.K_DOWN, ""),
            (pygame.K_a, "a"),
            (pygame.K_f, "f"),
            (pygame.K_q, "q"),
        )
        assert session.run_session(engine) == 0
    finally:
        pygame.display.quit()
    assert engine.frame().turn == 3


def test_a_dialogue_is_started_and_answered() -> None:
    engine = Engine.new(reference_pack(), seed=23)
    for _ in range(6):
        engine.step(Move("east"))
    engine.step(Move("enter"))
    pygame.display.init()
    try:
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=0, unicode=";"))
        _post_text("talk innkeeper")
        _post_keys((pygame.K_1, "1"), (pygame.K_q, "q"))
        assert session.run_session(engine) == 0
    finally:
        pygame.display.quit()
    assert engine.frame().mode == "dialogue"
    assert engine.frame().turn == 9
