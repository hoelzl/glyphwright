"""The GUI loop: paint, wait for one input, step, repeat (design 0011 §4, §7).

Turn-based like the TUI: input blocks, nothing repaints until the world
changes (or the typed bar echoes), and the loop holds no game state beyond
the rolling message log. The pump is driven by pygame's own event queue, so
a headless test posts events under the dummy video driver and exercises the
real loop. Clicks resolve against the Scene's targets (pure geometry); keys
resolve through the shared keymap or the typed bars.
"""

from __future__ import annotations

import textwrap

import pygame

from glyphwright.api import Engine
from glyphwright.frontends import keymap
from glyphwright.frontends.gui import paint, scene
from glyphwright.frontends.wire import decode_command
from glyphwright.harness import meta
from glyphwright.kernel.commands import Command

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


def _typed_command(
    engine: Engine,
    log: list[str],
    surface: pygame.Surface,
    key: str,
    *,
    harness: bool,
) -> Command | None:
    """One key resolved through the bars or the keymap; ``None`` when it
    meant nothing (or a bar handled everything itself)."""
    if key == ";":
        text = _read_line(engine, log, surface, "> ")
        if text is None:
            return None
        command = decode_command(text)
        if command is None:
            log.append(f"? unparsable: {text!r}")
        return command
    if key == ":":
        if not harness:
            log.append("? the meta-channel needs --harness")
            return None
        text = _read_line(engine, log, surface, ": ")
        if text is None:
            return None
        payload = meta.handle(engine, f":{text}")
        for line in meta.render_text(payload).splitlines():
            # The log region truncates at its width; wrap instead of
            # silently cutting a ':frame' dump short.
            log.extend(textwrap.wrap(line, scene.TEXT_COLS) or [""])
        return None
    return keymap.translate(key, engine.frame())


def run_session(
    engine: Engine,
    *,
    harness: bool = False,
    tiles: dict[str, pygame.Surface] | None = None,
) -> int:
    """Drive a run in a window until quit ('q' or closing the window)."""
    pygame.display.init()
    pygame.font.init()
    surface = pygame.display.set_mode(paint.WINDOW_SIZE)
    pygame.display.set_caption("GlyphWright")
    log: list[str] = []
    try:
        while True:
            composed = scene.compose(engine.frame(), tuple(log))
            paint.paint(composed, surface, tiles)
            pygame.display.flip()

            event = pygame.event.wait()
            if event.type == pygame.QUIT:
                return 0
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                command = scene.click(composed, event.pos)
            elif event.type == pygame.KEYDOWN:
                key = _key_name(event)
                if key is None:
                    continue
                if key == "q":
                    return 0
                command = _typed_command(engine, log, surface, key, harness=harness)
            else:
                continue
            if command is None:
                continue

            result = engine.step(command)
            if result.rejection is not None:
                log.append(f"? {result.rejection.reason}: {result.rejection.hint}")
            else:
                log.extend(result.frame.messages)
    finally:
        pygame.display.quit()
