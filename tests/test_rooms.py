"""Rooms and portals: the spatial abstraction's acid test (design 0003
sections 7.3, 7.4, 18.4). One game mixes a grid overworld with a room-graph
interior, and ``move <exit-token>`` is the only movement command everywhere."""

from __future__ import annotations

from glyphwright.api import Engine
from glyphwright.content.pack import reference_pack
from glyphwright.frames.frame import RoomView
from glyphwright.frontends import plain
from glyphwright.kernel.commands import Move, Take
from glyphwright.kernel.events import Moved
from glyphwright.kernel.state import PLAYER, fold
from glyphwright.world.roomgraph import Room, RoomGraphSpace
from glyphwright.world.space import PosId


def _engine() -> Engine:
    return Engine.new(reference_pack(), seed=13)


def _at_door() -> Engine:
    """Walk from (1,1) to the inn door at (7,1)."""
    engine = _engine()
    for _ in range(6):
        engine.step(Move("east"))
    return engine


def _inside() -> Engine:
    engine = _at_door()
    engine.step(Move("enter"))
    return engine


# -- the space itself ---------------------------------------------------------


def test_a_room_graph_space_answers_the_space_protocol() -> None:
    space = RoomGraphSpace(
        _area="keep",
        rooms=(
            Room(id="hall", name="Great Hall", description="Cold.", exits=()),
            Room(
                id="gate",
                name="Gatehouse",
                description="Drafty.",
                exits=(("north", "hall"),),
            ),
        ),
    )
    assert [str(p) for p in space.positions()] == ["keep:hall", "keep:gate"]
    gate = PosId(area="keep", local="gate")
    assert {t: str(p) for t, p in space.exits(gate).items()} == {"north": "keep:hall"}


def test_authored_exits_are_one_way_in_data() -> None:
    space = RoomGraphSpace(
        _area="keep",
        rooms=(
            Room(id="hall", name="Great Hall", description="Cold.", exits=()),
            Room(
                id="gate",
                name="Gatehouse",
                description="Drafty.",
                exits=(("north", "hall"),),
            ),
        ),
    )
    hall = PosId(area="keep", local="hall")
    assert space.exits(hall) == {}


# -- portals ------------------------------------------------------------------


def test_the_door_advertises_the_portal_exit() -> None:
    engine = _at_door()
    assert "enter" in engine.frame().commands.domains("move")[0]


def test_entering_the_inn_crosses_areas() -> None:
    engine = _at_door()
    result = engine.step(Move("enter"))
    assert result.accepted
    moved = next(e for e in result.events if isinstance(e, Moved))
    assert str(moved.destination) == "inn:common-room"
    at = engine._state.entity(PLAYER).at()
    assert at is not None and at.area == "inn"


def test_the_way_back_returns_to_the_same_tile() -> None:
    engine = _inside()
    engine.step(Move("out"))
    at = engine._state.entity(PLAYER).at()
    assert at is not None and str(at) == "village:7,1"


def test_room_to_room_movement_uses_authored_exits() -> None:
    engine = _inside()
    engine.step(Move("down"))
    at = engine._state.entity(PLAYER).at()
    assert at is not None and str(at) == "inn:cellar"
    engine.step(Move("up"))
    at = engine._state.entity(PLAYER).at()
    assert at is not None and str(at) == "inn:common-room"


# -- room frames --------------------------------------------------------------


def test_room_frames_use_the_room_viewport() -> None:
    engine = _inside()
    frame = engine.frame()
    assert isinstance(frame.viewport, RoomView)
    assert frame.viewport.area == "inn"
    assert frame.viewport.name
    assert frame.viewport.description
    assert set(frame.viewport.exits) == {"down", "out"}


def test_room_contents_list_items_and_actors_not_portals() -> None:
    engine = _inside()
    engine.step(Move("down"))
    viewport = engine.frame().viewport
    assert isinstance(viewport, RoomView)
    assert "rusty-key" in viewport.contents
    assert all("portal" not in c and "door" not in c for c in viewport.contents)


def test_items_can_be_taken_in_rooms() -> None:
    engine = _inside()
    engine.step(Move("down"))
    assert engine.frame().commands.domains("take") == (("rusty-key",),)
    result = engine.step(Take("rusty-key"))
    assert result.accepted
    inventory = engine._state.entity(PLAYER).inventory
    assert inventory is not None and "rusty-key" in inventory.items


def test_room_frames_render_and_round_trip_in_plain() -> None:
    engine = _inside()
    frame = engine.frame()
    rendered = plain.render(frame)
    assert plain.parse(rendered) == plain.project(frame)
    assert "Exits:" in rendered


def test_room_transcripts_carry_the_prose() -> None:
    engine = _at_door()
    frame = engine.step(Move("enter")).frame
    assert isinstance(frame.viewport, RoomView)
    rendered = plain.render(frame)
    assert frame.viewport.name in rendered
    assert frame.viewport.description in rendered


# -- determinism and fold -----------------------------------------------------


def test_area_crossing_folds_to_the_successor_state() -> None:
    engine = _at_door()
    before = engine._state
    result = engine.step(Move("enter"))
    assert fold(before, result.events) == engine._state


def test_mixed_world_walks_replay_identically() -> None:
    def run() -> list[object]:
        engine = Engine.new(reference_pack(), seed=31)
        script = ["east"] * 6 + ["enter", "down", "up", "out", "west"]
        return [engine.step(Move(token)).events for token in script]

    assert run() == run()


# -- cross-geometry combat and pursuit ---------------------------------------


def _with_cellar_rat(engine: Engine) -> Engine:
    from glyphwright.world.entities import Actor, AiBehavior, Entity, Position
    from glyphwright.world.roomgraph import RoomGraphSpace

    inn = engine._state.areas["inn"]
    assert isinstance(inn, RoomGraphSpace)
    rat = Entity(
        id="cellar-rat",
        position=Position(at=inn.pos("cellar")),
        actor=Actor(name="Rat", hp=2, max_hp=2, base_stats=(("atk", 1), ("def", 0))),
        ai=AiBehavior(hostile=True),
    )
    engine._state = engine._state.with_entity(rat)
    return engine


def test_room_melee_is_co_location_not_adjacent_rooms() -> None:
    """A hostile one room away is behind a wall; a hostile in the same room is
    at arm's length. The geometry answers, not the grid's adjacency rule."""
    engine = _with_cellar_rat(_inside())
    # Player in common-room, rat in the cellar below: no combat through floors.
    assert "attack" not in engine.frame().commands.verb_names()
    engine.step(Move("down"))
    # Co-located now: melee works, and the provoked rat fights.
    assert engine.frame().commands.domains("attack") == (("cellar-rat",),)


def test_flee_survives_hostiles_in_other_areas() -> None:
    """A battle flee must not crash on a hostile whose position lives in a
    different geometry (regression: cross-area PosId into GridSpace.exits)."""
    from glyphwright.kernel.commands import Flee

    engine = _with_cellar_rat(_engine())
    engine.step(Move("south"))  # bandit engages in the village
    assert engine._state.mode == "battle"
    result = engine.step(Flee())  # must not raise
    assert result.accepted


def test_an_aggroed_hostile_chases_through_the_portal() -> None:
    """The pursuit graph is the player's movement graph: a door the player
    can use is a door a pursuer can follow through."""
    from glyphwright.kernel.commands import Attack, Wait

    engine = _engine()
    engine.step(Move("east"))
    engine.step(Move("south"))  # (2,2): adjacent to the goblin
    engine.step(Attack("goblin-1"))  # make sure it is properly provoked
    engine.step(Move("north"))
    for _ in range(5):
        engine.step(Move("east"))  # run to the door at (7,1)
    engine.step(Move("enter"))
    at = engine._state.entity(PLAYER).at()
    assert at is not None and at.area == "inn"
    for _ in range(12):
        goblin = engine._state.entities.get("goblin-1")
        if goblin is None:
            break  # it died en route? impossible without combat — keep looping
        goblin_at = goblin.at()
        if goblin_at is not None and goblin_at.area == "inn":
            break
        engine.step(Wait())
    goblin = engine._state.entities.get("goblin-1")
    assert goblin is not None
    goblin_at = goblin.at()
    assert goblin_at is not None and goblin_at.area == "inn", (
        "an aggroed hostile must pursue through the portal"
    )


# -- content validation -------------------------------------------------------


def test_a_portal_leading_nowhere_fails_at_load() -> None:
    import pytest

    from glyphwright.content.pack import ContentPack
    from glyphwright.world.entities import Actor, Entity, Portal, Position
    from glyphwright.world.grid import GridSpace

    space = GridSpace.from_text("here", "..")
    player = Entity(
        id="player",
        position=Position(at=space.pos(0, 0)),
        actor=Actor(name="P", hp=1, max_hp=1),
    )
    bad = Entity(
        id="hole",
        position=Position(at=space.pos(1, 0)),
        portal=Portal(token="enter", to=PosId(area="typo", local="room")),
    )
    with pytest.raises(ValueError, match="leads nowhere"):
        ContentPack(name="broken", areas=(space,), entities=(player, bad))


def test_a_portal_may_not_shadow_a_geometric_exit() -> None:
    import pytest

    from glyphwright.content.pack import ContentPack
    from glyphwright.world.entities import Actor, Entity, Portal, Position
    from glyphwright.world.grid import GridSpace

    space = GridSpace.from_text("here", "..")
    player = Entity(
        id="player",
        position=Position(at=space.pos(1, 0)),
        actor=Actor(name="P", hp=1, max_hp=1),
    )
    shadowing = Entity(
        id="trap",
        position=Position(at=space.pos(0, 0)),
        portal=Portal(token="east", to=space.pos(1, 0)),
    )
    with pytest.raises(ValueError, match="shadows"):
        ContentPack(name="broken", areas=(space,), entities=(player, shadowing))


def test_duplicate_room_exit_tokens_fail_at_construction() -> None:
    import pytest

    with pytest.raises(ValueError, match="duplicate exit token"):
        RoomGraphSpace(
            _area="keep",
            rooms=(
                Room(
                    id="hall",
                    name="Hall",
                    description="Two norths.",
                    exits=(("north", "hall"), ("north", "hall")),
                ),
            ),
        )


def test_a_dead_end_room_still_round_trips() -> None:
    from glyphwright.frames.frame import PromptSpec, RoomView, SemanticFrame
    from glyphwright.kernel.commands import CommandGrammar

    frame = SemanticFrame(
        turn=3,
        mode="exploration",
        viewport=RoomView(
            area="keep",
            room="oubliette",
            name="The Oubliette",
            description="Smooth walls and no way back.",
            contents=(),
            exits=(),
        ),
        actors=(),
        messages=("You fall.",),
        prompt=PromptSpec(kind="command"),
        commands=CommandGrammar(verbs=(("look", ()),)),
    )
    rendered = plain.render(frame)
    assert "Exits: none." in rendered
    assert plain.parse(rendered) == plain.project(frame)
