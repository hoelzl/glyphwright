"""The GUI loop: paint, wait for one key, step, repeat (design 0011 §4, §7).

Turn-based like the TUI: input blocks, nothing repaints until the world
changes, and the loop holds no game state beyond the rolling message log.
The pump is driven by pygame's own event queue, so a headless test posts
events under the dummy video driver and exercises the real loop.
"""

from __future__ import annotations

import pygame

from glyphwright.api import Engine
from glyphwright.frontends import keymap
from glyphwright.frontends.gui import paint, scene

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


def run_session(engine: Engine) -> int:
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
            command = keymap.translate(key, engine.frame())
            if command is None:
                continue
            result = engine.step(command)
            if result.rejection is not None:
                log.append(f"? {result.rejection.reason}: {result.rejection.hint}")
            else:
                log.extend(result.frame.messages)
    finally:
        pygame.display.quit()
