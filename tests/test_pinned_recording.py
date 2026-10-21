"""The pinned recording replays: the engine's behaviour has not changed
without a rules bump (decision 0003)."""

from __future__ import annotations

import json

from regenerate_recordings import PIN, REGENERATE

from glyphwright.api import reference_pack
from glyphwright.harness.fingerprint import RULES
from glyphwright.harness.recording import replay


def _advice(problem: str) -> str:
    if problem.startswith("recorded against pack"):
        # Content is not behaviour: a pack change needs a new pin, not a bump.
        return f"The reference pack changed; run `{REGENERATE}` and commit the pin."
    return (
        "If the change is deliberate, bump RULES in "
        f"src/glyphwright/harness/fingerprint.py, run `{REGENERATE}`, and "
        "commit both (decision 0003)."
    )


def test_the_pinned_recording_replays() -> None:
    with PIN.open(encoding="utf-8") as source:
        outcome = replay(reference_pack(), source)
    assert outcome.ok, f"{outcome.problem}. {_advice(outcome.problem or '')}"


def test_the_pin_is_recorded_under_the_current_rules() -> None:
    header = json.loads(PIN.read_text(encoding="utf-8").splitlines()[0])
    assert header["rules"] == RULES, (
        f"RULES is {RULES} but the pin was recorded under {header['rules']}; "
        f"run `{REGENERATE}` and commit it"
    )
