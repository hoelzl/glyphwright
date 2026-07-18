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
from glyphwright.kernel.commands import (
    Attack,
    Command,
    Equip,
    Flee,
    Look,
    Move,
    Take,
    Use,
    Wait,
)

_EXITS = ("north", "east", "south", "west")
_ITEMS = ("potion-minor", "iron-sword", "no-such-item")

commands = st.one_of(
    st.sampled_from(_EXITS).map(Move),
    st.just(Look()),
    st.just(Wait()),
    st.just(Flee()),
    st.sampled_from(_ITEMS).map(Take),
    st.sampled_from(_ITEMS).map(Use),
    st.sampled_from(_ITEMS).map(Equip),
    st.sampled_from(("goblin-1", "bandit-1", "no-such-target")).map(Attack),
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


def test_the_pack_identity_derivation_is_pinned() -> None:
    """The pack-id scheme is part of the replay contract: recorded fingerprints
    must stay resolvable. Any refactor that shifts this hash — a component field
    rename, a serialization change — must be a deliberate, reviewed decision,
    which is exactly what breaking this pin forces."""
    from glyphwright.content.pack import ContentPack
    from glyphwright.world.entities import Actor, Entity, Position
    from glyphwright.world.grid import GridSpace

    space = GridSpace.from_text("pin", "..")
    entity = Entity(
        id="player",
        position=Position(at=space.pos(0, 0)),
        actor=Actor(name="Pin", hp=1, max_hp=1),
    )
    pack = ContentPack(name="pin", areas=(space,), entities=(entity,))
    # Re-pinned deliberately per slice when entity or area identity widens
    # (3A: AiBehavior; 4: Portal + full-area hashing; 6: Dialogue and
    # Openable; 7: abilities/statuses tables; 8: the pack-level player and
    # position preconditions reshaped the minimal pin pack; 9A: the fov
    # field widened grid-area identity) — a change
    # must show here.
    assert pack.pack_id == (
        "pin@sha256:ccf7915e64a1d57daadcdf51043782a0211e887e7bd6c105098ee1cf9a19d4bc"
    )


def test_content_changes_change_the_pack_id() -> None:
    from glyphwright.world.grid import GridSpace

    pack = reference_pack()
    # One tile turned to wall; everything else — including portal wiring —
    # stays valid, so this isolates the identity change to the content change.
    altered_map = "#########\n#.......#\n#..##..##\n#.......#\n#########"
    altered = type(pack)(
        name=pack.name,
        areas=(GridSpace.from_text("village", altered_map), *pack.areas[1:]),
        entities=pack.entities,
        abilities=pack.abilities,
        statuses=pack.statuses,
    )
    assert altered.pack_id != pack.pack_id, "a content change must invalidate baselines"
