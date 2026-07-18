"""Deterministic golden scenarios shared by the golden test and its
regenerator. Run as a script to rewrite ``tests/goldens/``; the diff is then
reviewed by a human before committing (design 0003 §17)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from glyphwright.api import Engine
from glyphwright.content.pack import reference_pack
from glyphwright.frontends import plain
from glyphwright.frontends.gui import scene
from glyphwright.frontends.tui import render
from glyphwright.kernel.commands import Move


def _engine() -> Engine:
    return Engine.new(reference_pack(), seed=424242)


def _tui_village() -> str:
    engine = _engine()
    engine.step(Move("east"))
    return render.paint(engine.frame(), ("You go east.",))


def _tui_inn() -> str:
    engine = _engine()
    for _ in range(6):
        engine.step(Move("east"))
    engine.step(Move("enter"))
    return render.paint(engine.frame(), ("You go enter.",))


def _tui_battle() -> str:
    engine = _engine()
    engine.step(Move("south"))
    return render.paint(engine.frame(), ())


def _plain_village() -> str:
    engine = _engine()
    frame = engine.step(Move("east")).frame
    return plain.render(frame) + "\n"


def _plain_inn() -> str:
    engine = _engine()
    for _ in range(6):
        engine.step(Move("east"))
    frame = engine.step(Move("enter")).frame
    return plain.render(frame) + "\n"


def _gui_village() -> str:
    engine = _engine()
    frame = engine.step(Move("east")).frame
    return scene.scene_text(scene.compose(frame, frame.messages))


def _gui_inn() -> str:
    engine = _engine()
    for _ in range(6):
        engine.step(Move("east"))
    frame = engine.step(Move("enter")).frame
    return scene.scene_text(scene.compose(frame, frame.messages))


def _gui_battle() -> str:
    engine = _engine()
    frame = engine.step(Move("south")).frame
    return scene.scene_text(scene.compose(frame, frame.messages))


GOLDENS: dict[str, Callable[[], str]] = {
    "tui_village": _tui_village,
    "tui_inn": _tui_inn,
    "tui_battle": _tui_battle,
    "plain_village": _plain_village,
    "plain_inn": _plain_inn,
    "gui_village": _gui_village,
    "gui_inn": _gui_inn,
    "gui_battle": _gui_battle,
}


def render_golden(name: str) -> str:
    return GOLDENS[name]()


def main() -> None:  # pragma: no cover - invoked by humans
    golden_dir = Path(__file__).resolve().parent / "goldens"
    golden_dir.mkdir(exist_ok=True)
    for name, scenario in GOLDENS.items():
        (golden_dir / f"{name}.txt").write_text(
            scenario(), encoding="utf-8", newline=""
        )
        print(f"wrote {name}.txt")


if __name__ == "__main__":  # pragma: no cover
    main()
