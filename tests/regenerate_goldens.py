"""Golden scenarios shared by the golden test and its regenerator.

Run as a script to rewrite ``tests/goldens/``, then review the diff by eye
before committing: the diff is the review::

    uv run python tests/regenerate_goldens.py
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from glyphwright.api import Engine, reference_pack
from glyphwright.frontends import plain
from glyphwright.kernel.commands import Move

GOLDEN_DIR = Path(__file__).resolve().parent / "goldens"


def _plain_village() -> str:
    engine = Engine.new(reference_pack(), seed=424242)
    engine.step(Move("east"))
    frame = engine.step(Move("south")).frame
    return plain.render(frame) + "\n"


GOLDENS: dict[str, Callable[[], str]] = {
    "plain_village": _plain_village,
}


def render_golden(name: str) -> str:
    return GOLDENS[name]()


if __name__ == "__main__":
    GOLDEN_DIR.mkdir(exist_ok=True)
    for name in GOLDENS:
        path = GOLDEN_DIR / f"{name}.txt"
        path.write_text(render_golden(name), encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(GOLDEN_DIR.parent.parent).as_posix()}")
