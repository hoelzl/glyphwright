"""Determinism is a contract: a run is fixed by (pack, seed, commands).

These are the tests that make replay, shrinking, and reviewed baselines
meaningful (design 0003 sections 5.4 and 17).
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from glyphwright.api import Engine, StepResult
from glyphwright.content.pack import reference_pack
from glyphwright.frontends.wire import encode_frame
from glyphwright.kernel.commands import Command, Look, Move, Wait

_EXITS = ("north", "east", "south", "west")

commands = st.one_of(
    st.sampled_from(_EXITS).map(Move),
    st.just(Look()),
    st.just(Wait()),
)


def _run(seed: int, script: list[Command]) -> list[StepResult]:
    engine = Engine.new(reference_pack(), seed=seed)
    return [engine.step(command) for command in script]


def _frames(results: list[StepResult]) -> list[object]:
    return [encode_frame(result.frame) for result in results]


@settings(max_examples=50, deadline=None)
@given(script=st.lists(commands, max_size=25))
def test_same_pack_seed_and_commands_give_the_same_frames(
    script: list[Command],
) -> None:
    assert _frames(_run(1, script)) == _frames(_run(1, script))


@settings(max_examples=50, deadline=None)
@given(script=st.lists(commands, max_size=25))
def test_same_pack_seed_and_commands_give_the_same_events(
    script: list[Command],
) -> None:
    first = [result.events for result in _run(1, script)]
    second = [result.events for result in _run(1, script)]
    assert first == second


@settings(max_examples=30, deadline=None)
@given(script=st.lists(commands, min_size=1, max_size=20))
def test_snapshot_restore_resumes_the_identical_run(script: list[Command]) -> None:
    engine = Engine.new(reference_pack(), seed=99)
    split = len(script) // 2
    for command in script[:split]:
        engine.step(command)

    resumed = Engine.restore(engine.snapshot())
    expected = [encode_frame(engine.step(c).frame) for c in script[split:]]
    actual = [encode_frame(resumed.step(c).frame) for c in script[split:]]
    assert actual == expected


@settings(max_examples=30, deadline=None)
@given(script=st.lists(commands, max_size=20))
def test_a_snapshot_does_not_alias_the_live_run(script: list[Command]) -> None:
    engine = Engine.new(reference_pack(), seed=3)
    snapshot = engine.snapshot()
    frozen = encode_frame(Engine.restore(snapshot).frame())
    for command in script:
        engine.step(command)
    assert encode_frame(Engine.restore(snapshot).frame()) == frozen


def test_the_fingerprint_records_what_produced_the_evidence() -> None:
    engine = Engine.new(reference_pack(), seed=424242)
    fingerprint = engine.fingerprint()
    assert fingerprint.seed == 424242
    assert fingerprint.pack.startswith("reference-vale@sha256:")
    assert fingerprint.engine.startswith("glyphwright ")


def test_content_changes_change_the_pack_id() -> None:
    from glyphwright.world.grid import GridSpace

    pack = reference_pack()
    altered = type(pack)(
        name=pack.name,
        areas=(GridSpace.from_text("village", "###\n#.#\n###"),),
        entities=pack.entities,
    )
    assert altered.pack_id != pack.pack_id, "a content change must invalidate baselines"
