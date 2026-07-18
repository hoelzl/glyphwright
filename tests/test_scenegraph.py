"""The SceneGraph seam: ``compose(frame, manifest) -> SceneGraph`` (0012 §3).

The SceneGraph is frozen, pygame-free, engine-free data naming everything a
presentation will realize: ordered placements with their tier, a camera, the
transition descriptors for cosmetic animation, and the input affordances
minted from the grammar. Goldens and projection-consistency run with no
renderer installed — the same split as 0011, but the evidence is now a scene
graph rather than a cell grid.
"""

from __future__ import annotations

from glyphwright.api import Engine
from glyphwright.content.pack import reference_pack
from glyphwright.frontends.presentation.manifest import PresentationManifest
from glyphwright.kernel.commands import Move


def _manifest() -> PresentationManifest:
    return PresentationManifest(bindings={}, decoration={}, hints={})


def _engine() -> Engine:
    return Engine.new(reference_pack(), seed=424242)


_TIER_RANK = {"ground": 0, "fixture": 1, "actor": 2}


def test_a_grid_frame_composes_placements_for_every_tier() -> None:
    from glyphwright.frontends.presentation import scenegraph

    graph = scenegraph.compose(_engine().frame(), _manifest())
    # The player's cell carries both its ground and the actor on it.
    player_layers = [p for p in graph.placements if p.semantic_pos == "village:1,1"]
    glyphs = {p.glyph for p in player_layers}
    assert "." in glyphs and "@" in glyphs


def test_placements_are_ordered_ground_then_fixture_then_actor() -> None:
    from glyphwright.frontends.presentation import scenegraph

    graph = scenegraph.compose(_engine().frame(), _manifest())
    tiers = [p.tier for p in graph.placements]
    # Ground placements never come after an actor placement in the order.
    assert tiers == sorted(tiers, key=_TIER_RANK.__getitem__)


def test_each_placement_names_its_semantic_and_render_position() -> None:
    from glyphwright.frontends.presentation import scenegraph

    graph = scenegraph.compose(_engine().frame(), _manifest())
    for placement in graph.placements:
        area, _, local = placement.semantic_pos.partition(":")
        assert area and local, placement.semantic_pos
        # render_pos is a 3-tuple (x, y, z); z rides render_pos, not tier (§4).
        assert len(placement.render_pos) == 3


def test_the_camera_is_a_deterministic_function_of_the_frame() -> None:
    from glyphwright.frontends.presentation import scenegraph

    first = scenegraph.compose(_engine().frame(), _manifest())
    second = scenegraph.compose(_engine().frame(), _manifest())
    assert first.camera == second.camera


def test_move_events_become_transition_descriptors() -> None:
    from glyphwright.frontends.presentation import scenegraph

    engine = _engine()
    result = engine.step(Move("east"))
    graph = scenegraph.compose(result.frame, _manifest(), events=result.events)
    moves = [t for t in graph.transitions if t.kind == "move"]
    assert moves, "a Moved event must yield a move transition descriptor"
    assert moves[0].glyph == "@"


def test_equal_frames_compose_equal_graphs() -> None:
    from glyphwright.frontends.presentation import scenegraph

    assert scenegraph.compose(_engine().frame(), _manifest()) == scenegraph.compose(
        _engine().frame(), _manifest()
    )


def test_the_graph_carries_the_manifest_hash() -> None:
    from glyphwright.frontends.presentation import scenegraph

    graph = scenegraph.compose(_engine().frame(), _manifest())
    assert graph.manifest_hash.startswith("sha256:")


def test_projection_consistency_topmost_placement_matches_flatten() -> None:
    """The bridge: the agent's flat observation and the human's layered scene
    are two projections of one run. At every cell, the *topmost* placement the
    SceneGraph would draw is exactly the glyph ``flatten`` shows the agent
    (0012 §2). If these diverge, the two observers see different games."""
    _assert_bridge(_engine().frame())


def test_projection_consistency_holds_through_fov_fog() -> None:
    """The warren's fog (`fov=3`) marks unseen ground ``?``; those cells flow
    through placements and must still satisfy the bridge — fog is a
    presentation of the same one run, not a second game."""
    engine = _engine()
    for _ in range(6):
        engine.step(Move("east"))
    engine.step(Move("south"))
    engine.step(Move("south"))
    engine.step(Move("down"))  # into the warren
    _assert_bridge(engine.frame())


def _assert_bridge(frame: object) -> None:
    """At every cell, topmost placement == the flatten() glyph (0012 §2)."""
    from glyphwright.frames.frame import GridView, SemanticFrame, flatten
    from glyphwright.frontends.presentation import scenegraph

    assert isinstance(frame, SemanticFrame)
    assert isinstance(frame.viewport, GridView)
    graph = scenegraph.compose(frame, _manifest())

    # The topmost tier present at each (x, y), from the placements.
    topmost: dict[tuple[int, int], str] = {}
    for placement in graph.placements:  # ordered ground->fixture->actor
        x, y, _ = placement.render_pos
        topmost[(x, y)] = placement.glyph

    flat = flatten(frame.viewport)
    for y, row in enumerate(flat):
        for x, glyph in enumerate(row):
            if glyph == " ":
                continue
            assert topmost.get((x, y)) == glyph, (
                f"cell {(x, y)}: scene shows {topmost.get((x, y))!r}, "
                f"flatten shows {glyph!r}"
            )
