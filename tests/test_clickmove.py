"""Click-to-move compiles a clicked position into move commands (0012 §6).

The human clicks a reachable cell; the frontend expands that into the
deterministic ``move <token>`` sequence the pathfinder computes, each step a
real kernel command. The agent never needs the macro. A click session is
therefore byte-identical to having typed the moves — which the replay test
proves through the recording harness.
"""

from __future__ import annotations

import io

from glyphwright.api import Engine
from glyphwright.content.pack import reference_pack
from glyphwright.kernel.commands import Move


def _engine(seed: int = 424242) -> Engine:
    return Engine.new(reference_pack(), seed=seed)


def test_a_click_on_an_adjacent_floor_expands_to_one_move() -> None:
    from glyphwright.frontends.presentation.clickmove import expand_click

    engine = _engine()
    # The player starts at village:1,1; 2,1 is open floor to the east.
    assert expand_click(engine, "village", (2, 1)) == (Move("east"),)


def test_a_click_several_cells_away_expands_to_a_token_sequence() -> None:
    from glyphwright.frontends.presentation.clickmove import expand_click

    engine = _engine()
    tokens = expand_click(engine, "village", (4, 1))
    assert tokens is not None and len(tokens) == 3
    assert all(isinstance(step, Move) for step in tokens)


def test_a_click_on_a_wall_expands_to_nothing() -> None:
    from glyphwright.frontends.presentation.clickmove import expand_click

    engine = _engine()
    assert expand_click(engine, "village", (0, 0)) is None


def test_a_click_off_the_map_expands_to_nothing() -> None:
    from glyphwright.frontends.presentation.clickmove import expand_click

    engine = _engine()
    assert expand_click(engine, "village", (99, 99)) is None


def test_a_click_on_the_players_own_cell_is_an_empty_path_not_none() -> None:
    """Already-there is *not* unreachable: ``()`` says 'no moves needed', while
    ``None`` says 'cannot get there'. A frontend branches on the difference."""
    from glyphwright.frontends.presentation.clickmove import expand_click

    engine = _engine()
    assert expand_click(engine, "village", (1, 1)) == ()


def test_a_click_in_a_fogged_area_still_expands_via_live_topology() -> None:
    """The macro types only moves an agent could type, and the kernel validates
    each step — so a fogged (FOV-obscured) cell expands like any other. This is
    a conscious, tested choice, not an emergent leak: the oracle an agent reads
    is equally free to plan through fog."""
    from glyphwright.frontends.presentation.clickmove import expand_click

    engine = _engine()
    # Reach the FOV-fogged warren: across the village's open north row to the
    # hole at village:7,3 (staying clear of the hostiles on row 3's west), then
    # down. The warren has fov=3; the far cell (5,2) sits beyond first sight.
    for _ in range(6):  # village:1,1 -> 7,1
        engine.step(Move("east"))
    engine.step(Move("south"))  # 7,2
    engine.step(Move("south"))  # 7,3, the hole
    engine.step(Move("down"))  # warren:1,1
    steps = expand_click(engine, "warren", (5, 2))
    assert steps is not None


def test_the_expansion_actually_arrives_when_executed() -> None:
    """The macro's promises are real: stepping the expanded moves moves the
    player to the clicked position (kernel-validated, one token at a time)."""
    from glyphwright.frontends.presentation.clickmove import expand_click

    engine = _engine()
    steps = expand_click(engine, "village", (4, 1))
    assert steps is not None
    for step in steps:
        result = engine.step(step)
        assert result.rejection is None, result.rejection
    player = next(actor for actor in engine.frame().actors if actor.id == "player")
    assert player.at.local == "4,1"


def test_a_click_session_replays_byte_identically() -> None:
    """The bridge claim: a human's click-driven run and an agent's typed run
    are the same run. Record the click session; replay must reproduce the
    exact final state, RNG cursor included (0003 §5, design 0008)."""
    from glyphwright.frontends.presentation.clickmove import expand_click
    from glyphwright.harness.recording import RecordingEngine, replay

    sink = io.StringIO()
    engine = RecordingEngine.recording(reference_pack(), seed=77, sink=sink)
    for target in ("village", (4, 1)), ("village", (4, 3)):
        steps = expand_click(engine, target[0], target[1])
        assert steps is not None
        for step in steps:
            engine.step(step)

    outcome = replay(reference_pack(), sink.getvalue().splitlines())
    assert outcome.ok, outcome.problem
    assert outcome.engine is not None
    assert outcome.engine.snapshot() == engine.snapshot()
