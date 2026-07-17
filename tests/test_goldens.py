"""Reviewed golden snapshots: the small set of rendered outputs a human has
looked at and blessed (design 0003 §17). These catch layout regressions in
derived output; semantic changes belong in frames and events, not here.

To regenerate after a deliberate layout change:

    uv --no-config run python tests/regenerate_goldens.py

then review the diff by eye before committing — the diff *is* the review.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from regenerate_goldens import GOLDENS, render_golden

GOLDEN_DIR = Path(__file__).resolve().parent / "goldens"


@pytest.mark.parametrize("name", sorted(GOLDENS))
def test_rendered_output_matches_the_blessed_golden(name: str) -> None:
    # newline="" preserves the TUI's \r\n bytes; goldens are byte contracts.
    with (GOLDEN_DIR / f"{name}.txt").open(encoding="utf-8", newline="") as file:
        blessed = file.read()
    assert render_golden(name) == blessed, (
        f"{name} drifted; if the layout change is deliberate, regenerate "
        "the goldens and review the diff"
    )


def test_every_golden_on_disk_is_generated() -> None:
    on_disk = {path.stem for path in GOLDEN_DIR.glob("*.txt")}
    assert on_disk == set(GOLDENS)
