"""Reviewed golden snapshots: rendered outputs a human has looked at and blessed.

These catch layout regressions in derived output; semantic changes belong in
frames and events, not here. After a deliberate layout change, regenerate with
``uv run python tests/regenerate_goldens.py`` and review the diff.
"""

from __future__ import annotations

import pytest
from regenerate_goldens import GOLDEN_DIR, GOLDENS, render_golden


@pytest.mark.parametrize("name", sorted(GOLDENS))
def test_rendered_output_matches_the_blessed_golden(name: str) -> None:
    # newline="" keeps the file's bytes: a golden is a byte contract.
    with (GOLDEN_DIR / f"{name}.txt").open(encoding="utf-8", newline="") as file:
        blessed = file.read()
    assert render_golden(name) == blessed, (
        f"{name} drifted; if the layout change is deliberate, regenerate the "
        "goldens and review the diff"
    )


def test_every_golden_on_disk_is_generated() -> None:
    assert {path.stem for path in GOLDEN_DIR.glob("*.txt")} == set(GOLDENS)
