"""The pinned recording replays: the engine's behaviour has not changed
without a rules bump (decision 0003)."""

from __future__ import annotations

import json

from regenerate_recordings import PIN, REGENERATE, render

from glyphwright.api import reference_pack
from glyphwright.frontends.wire import VERB_SPECS
from glyphwright.harness.fingerprint import RULES
from glyphwright.harness.recording import replay

_BUMP = (
    "bump RULES in src/glyphwright/harness/fingerprint.py, run "
    f"`{REGENERATE}`, and commit both (decision 0003)"
)


def _advice(problem: str) -> str:
    # Replay itself says whether a pack change came with new events.
    if problem.endswith("only the pack changed: re-record"):
        return f"Only run `{REGENERATE}` and commit the pin."
    return f"If the change is deliberate, {_BUMP}."


def test_the_pinned_recording_replays() -> None:
    lines = PIN.read_text(encoding="utf-8").splitlines()
    outcome = replay(reference_pack(), lines)
    assert outcome.ok, f"{outcome.problem}. {_advice(outcome.problem or '')}"


def test_the_pin_is_recorded_under_the_current_rules() -> None:
    header = json.loads(PIN.read_text(encoding="utf-8").splitlines()[0])
    assert header["rules"] == RULES, (
        f"RULES is {RULES} but the pin was recorded under {header['rules']}; "
        f"run `{REGENERATE}` and commit it"
    )


def test_the_tour_uses_every_verb() -> None:
    # The workshop dry run made `wait` heal, and the check still passed: the
    # tour never waited, so the pin could not notice.
    steps = [json.loads(line) for line in PIN.read_text(encoding="utf-8").splitlines()]
    used = {step["command"].split()[0] for step in steps[1:]}
    assert set(VERB_SPECS) <= used, (
        f"the tour never uses {sorted(set(VERB_SPECS) - used)}; add them "
        f"to tests/regenerate_recordings.py and run `{REGENERATE}`"
    )


def _against_an_old_pack_id(*, tamper: bool) -> list[str]:
    # A fresh recording, not the committed pin, so these tests say nothing
    # when the pin itself fails for another reason.
    lines = render().splitlines()
    lines[0] = json.dumps(json.loads(lines[0]) | {"pack": "old@sha256:00"})
    if tamper:
        step = json.loads(lines[1]) | {"events": "sha256:" + "0" * 64}
        lines[1] = json.dumps(step)
    return lines


def test_a_pack_id_change_alone_needs_only_a_re_record() -> None:
    problem = replay(reference_pack(), _against_an_old_pack_id(tamper=False)).problem
    assert problem is not None
    assert "Only run" in _advice(problem)


def test_a_pack_id_change_with_new_events_needs_a_rules_bump() -> None:
    # The agent gate found the old advice hid the bump in exactly this case.
    problem = replay(reference_pack(), _against_an_old_pack_id(tamper=True)).problem
    assert problem is not None
    assert problem.endswith("the behaviour changed as well")
    assert "bump RULES" in _advice(problem)
