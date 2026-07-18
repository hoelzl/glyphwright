"""The GUI loop: paint, wait for one key, step, repeat (design 0011 §4, §7).

Turn-based like the TUI: input blocks, nothing repaints until the world
changes (or the typed bar echoes), and the loop holds no game state beyond
the rolling message log. The pump is driven by pygame's own event queue, so
a headless test posts events under the dummy video driver and exercises the
real loop.
"""

from __future__ import annotations

import textwrap

import pygame

from glyphwright.api import Engine
from glyphwright.frontends import keymap
from glyphwright.frontends.gui import paint, scene
from glyphwright.frontends.wire import decode_command
from glyphwright.harness import meta

_ARROWS = {
    pygame.K_UP: "UP",
    pygame.K_DOWN: "DOWN",
    pygame.K_LEFT: "LEFT",
    pygame.K_RIGHT: "RIGHT",
}


def _key_name(event: pygame.event.Event) -> str | None:
    """Normalize one KEYDOWN into the shared keymap's key names."""
    name = _ARROWS.get(event.key)
    if name is not None:
        return name
    typed: str = event.unicode
    if typed and typed.isprintable():
        return typed
    return None


def _read_line(
    engine: Engine, log: list[str], surface: pygame.Surface, prompt: str
) -> str | None:
    """Collect typed characters until Enter, echoing through the bar.

    ``None`` means the bar was cancelled (Escape, or the window closing —
    the QUIT event is re-posted so the outer loop still sees it).
    """
    collected = ""
    while True:
        paint.paint(
            scene.compose(engine.frame(), tuple(log), bar=prompt + collected),
            surface,
        )
        pygame.display.flip()
        event = pygame.event.wait()
        if event.type == pygame.QUIT:
            pygame.event.post(pygame.event.Event(pygame.QUIT))
            return None
        if event.type != pygame.KEYDOWN:
            continue
        if event.key == pygame.K_RETURN:
            return collected
        if event.key == pygame.K_ESCAPE:
            return None
        if event.key == pygame.K_BACKSPACE:
            collected = collected[:-1]
            continue
        typed: str = event.unicode
        if typed and typed.isprintable():
            collected += typed


def run_session(engine: Engine, *, harness: bool = False) -> int:
    """Drive a run in a window until quit ('q' or closing the window)."""
    pygame.display.init()
    pygame.font.init()
    surface = pygame.display.set_mode(paint.WINDOW_SIZE)
    pygame.display.set_caption("GlyphWright")
    log: list[str] = []
    try:
        while True:
            paint.paint(scene.compose(engine.frame(), tuple(log)), surface)
            pygame.display.flip()

            event = pygame.event.wait()
            if event.type == pygame.QUIT:
                return 0
            if event.type != pygame.KEYDOWN:
                continue
            key = _key_name(event)
            if key is None:
                continue
            if key == "q":
                return 0

            if key == ";":
                text = _read_line(engine, log, surface, "> ")
                if text is None:
                    continue
                command = decode_command(text)
                if command is None:
                    log.append(f"? unparsable: {text!r}")
                    continue
            elif key == ":":
                if not harness:
                    log.append("? the meta-channel needs --harness")
                    continue
                text = _read_line(engine, log, surface, ": ")
                if text is None:
                    continue
                payload = meta.handle(engine, f":{text}")
                for line in meta.render_text(payload).splitlines():
                    # The log region truncates at its width; wrap instead of
                    # silently cutting a ':frame' dump short.
                    log.extend(textwrap.wrap(line, scene.TEXT_COLS) or [""])
                continue
            else:
                maybe = keymap.translate(key, engine.frame())
                if maybe is None:
                    continue
                command = maybe

            result = engine.step(command)
            if result.rejection is not None:
                log.append(f"? {result.rejection.reason}: {result.rejection.hint}")
            else:
                log.extend(result.frame.messages)
    finally:
        pygame.display.quit()
