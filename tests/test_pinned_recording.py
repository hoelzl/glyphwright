"""The pinned recording replays: the engine's behaviour has not changed
without a rules bump (decision 0003)."""

from __future__ import annotations

import json

from regenerate_recordings import PIN, REGENERATE

from glyphwright.api import reference_pack
from glyphwright.harness.fingerprint import RULES
from glyphwright.harness.recording import replay

_BUMP = (
    "bump RULES in src/glyphwright/harness/fingerprint.py, run "
    f"`{REGENERATE}`, and commit both (decision 0003)"
)


def _events_changed_under_the_new_pack_id(lines: list[str]) -> str | None:
    """Replay the pin's steps as if recorded against today's pack id.

    A pack id changes with the content and with ``Entity``'s shape; neither is
    behaviour. Only the steps say whether the events changed as well.
    """
    header = json.loads(lines[0]) | {"pack": reference_pack().pack_id}
    return replay(reference_pack(), [json.dumps(header), *lines[1:]]).problem


def _advice(problem: str, lines: list[str]) -> str:
    if not problem.startswith("recorded against pack"):
        return f"If the change is deliberate, {_BUMP}."
    changed = _events_changed_under_the_new_pack_id(lines)
    if changed is None:
        return (
            "The pack id changed but every step's events did not; "
            f"only run `{REGENERATE}` and commit the pin."
        )
    return f"The pack id changed, and so did the events ({changed}): {_BUMP}."


def test_the_pinned_recording_replays() -> None:
    lines = PIN.read_text(encoding="utf-8").splitlines()
    outcome = replay(reference_pack(), lines)
    assert outcome.ok, f"{outcome.problem}. {_advice(outcome.problem or '', lines)}"


def test_the_pin_is_recorded_under_the_current_rules() -> None:
    header = json.loads(PIN.read_text(encoding="utf-8").splitlines()[0])
    assert header["rules"] == RULES, (
        f"RULES is {RULES} but the pin was recorded under {header['rules']}; "
        f"run `{REGENERATE}` and commit it"
    )


def _against_an_old_pack_id(*, tamper: bool) -> list[str]:
    lines = PIN.read_text(encoding="utf-8").splitlines()
    lines[0] = json.dumps(json.loads(lines[0]) | {"pack": "old@sha256:00"})
    if tamper:
        step = json.loads(lines[1]) | {"events": "sha256:" + "0" * 64}
        lines[1] = json.dumps(step)
    return lines


def test_a_pack_id_change_alone_needs_only_a_re_record() -> None:
    lines = _against_an_old_pack_id(tamper=False)
    problem = replay(reference_pack(), lines).problem
    assert problem is not None
    assert "only run" in _advice(problem, lines)


def test_a_pack_id_change_with_new_events_needs_a_rules_bump() -> None:
    # The agent gate found the old advice hid the bump in exactly this case.
    lines = _against_an_old_pack_id(tamper=True)
    problem = replay(reference_pack(), lines).problem
    assert problem is not None
    assert "bump RULES" in _advice(problem, lines)
