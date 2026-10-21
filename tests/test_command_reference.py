"""The command reference is generated, and stays in step with the code."""

from __future__ import annotations

from pathlib import Path

import pytest

from glyphwright.harness import reference

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("api.py", "frontends/jsonl.py", "harness/meta.py")


def test_the_committed_reference_matches_a_fresh_render() -> None:
    committed = (ROOT / reference.PAGE).read_text(encoding="utf-8")
    assert committed == reference.render(), (
        f"{reference.PAGE} is stale; run `{reference.REGENERATE}` and commit it"
    )


@pytest.mark.parametrize(
    "reason", [reason for reason, _, _ in reference.GENERAL_REASONS]
)
def test_every_general_reason_is_emitted_somewhere(reason: str) -> None:
    code = "".join(
        (ROOT / "src" / "glyphwright" / name).read_text(encoding="utf-8")
        for name in SOURCES
    )
    assert f'"{reason}"' in code, f"{reason} is documented but never emitted"
