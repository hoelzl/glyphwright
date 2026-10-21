"""World state and grid geometry: immutability, the fold, and blocking rules."""

from __future__ import annotations

import dataclasses

import pytest

from glyphwright.kernel.events import MoveBlocked, Moved, TurnAdvanced
from glyphwright.kernel.rng import Rng
from glyphwright.kernel.state import MODE_EXPLORATION, PLAYER, WorldState, fold
from glyphwright.world.entities import (
    Actor,
    Blocker,
    Entity,
    Equipment,
    Position,
    Renderable,
    StatModifier,
)
from glyphwright.world.grid import GridSpace, coords
from glyphwright.world.space import PosId, Space

ROOM = GridSpace.from_text("room", "#####\n#...#\n#...#\n#####")


def _actor(entity_id: str, x: int, y: int, *, blocks: bool = False) -> Entity:
    return Entity(
        id=entity_id,
        position=Position(at=ROOM.pos(x, y)),
        actor=Actor(name=entity_id.title(), hp=5, max_hp=5),
        blocker=Blocker() if blocks else None,
        renderable=Renderable(glyph=entity_id[0], label=entity_id),
    )


@pytest.fixture
def state() -> WorldState:
    return WorldState(
        entities={
            PLAYER: _actor(PLAYER, 1, 1),
            "rock": _actor("rock", 3, 1, blocks=True),
        },
        areas={"room": ROOM},
        mode_stack=(MODE_EXPLORATION,),
        turn=0,
        rng=Rng.from_seed(1),
    )


def test_a_grid_space_satisfies_the_space_protocol() -> None:
    assert isinstance(ROOM, Space)


def test_grid_positions_round_trip_through_their_identifiers() -> None:
    pos = ROOM.pos(2, 1)
    assert str(pos) == "room:2,1"
    assert PosId.parse("room:2,1") == pos
    assert coords(pos) == (2, 1)


@pytest.mark.parametrize("text", ["room", "room:", ":1,1"])
def test_malformed_position_identifiers_are_rejected(text: str) -> None:
    with pytest.raises(ValueError):
        PosId.parse(text)


def test_exits_are_topology_including_walls() -> None:
    assert set(ROOM.exits(ROOM.pos(1, 1))) == {"north", "east", "south", "west"}
    assert set(ROOM.exits(ROOM.pos(0, 0))) == {"east", "south"}


def test_blocked_reasons_name_wall_occupied_and_edge(state: WorldState) -> None:
    assert ROOM.blocked_reason(state, ROOM.pos(0, 1), PLAYER) == "wall"
    assert ROOM.blocked_reason(state, ROOM.pos(3, 1), PLAYER) == "occupied"
    assert ROOM.blocked_reason(state, ROOM.pos(9, 9), PLAYER) == "edge"
    assert ROOM.blocked_reason(state, ROOM.pos(2, 1), PLAYER) is None


def test_a_blocker_does_not_block_itself(state: WorldState) -> None:
    assert ROOM.passable(state, ROOM.pos(3, 1), "rock")


@pytest.mark.parametrize(
    "rows",
    [(), ("",), ("..", "."), ("x",)],
    ids=["empty", "blank", "ragged", "unknown-glyph"],
)
def test_malformed_grids_are_rejected(rows: tuple[str, ...]) -> None:
    with pytest.raises(ValueError):
        GridSpace(_area="bad", rows=rows)


def test_state_is_deeply_immutable(state: WorldState) -> None:
    with pytest.raises(TypeError):
        state.entities["player"] = None  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.turn = 99  # type: ignore[misc]


def test_the_mode_stack_never_empties(state: WorldState) -> None:
    assert state.mode == MODE_EXPLORATION
    with pytest.raises(ValueError):
        dataclasses.replace(state, mode_stack=())


def test_entities_at_is_sorted_by_id(state: WorldState) -> None:
    crowded = state.with_entity(_actor("ant", 1, 1))
    assert [e.id for e in crowded.entities_at(ROOM.pos(1, 1))] == ["ant", PLAYER]


def test_a_moved_event_relocates_the_actor(state: WorldState) -> None:
    moved = Moved(
        actor=PLAYER, origin=ROOM.pos(1, 1), destination=ROOM.pos(2, 1), exit="east"
    )
    assert fold(state, (moved,)).entity(PLAYER).at() == ROOM.pos(2, 1)


def test_a_blocked_move_changes_nothing(state: WorldState) -> None:
    blocked = MoveBlocked(
        actor=PLAYER, origin=ROOM.pos(1, 1), exit="north", reason="wall"
    )
    assert fold(state, (blocked,)) == state


def test_turn_advanced_carries_the_rng_cursor(state: WorldState) -> None:
    _, later = state.rng.next_u64()
    folded = fold(state, (TurnAdvanced(turn=1, rng=later.encode()),))
    assert folded.turn == 1
    assert folded.rng == later


def test_turn_advanced_without_a_cursor_keeps_the_rng(state: WorldState) -> None:
    folded = fold(state, (TurnAdvanced(turn=1),))
    assert folded.rng == state.rng


def test_folding_does_not_mutate_its_input(state: WorldState) -> None:
    before = state.entity(PLAYER).at()
    moved = Moved(
        actor=PLAYER, origin=ROOM.pos(1, 1), destination=ROOM.pos(2, 1), exit="east"
    )
    fold(state, (moved,))
    assert state.entity(PLAYER).at() == before


def test_equipment_keeps_one_item_per_slot_sorted_by_slot() -> None:
    worn = Equipment().with_slot("weapon", "sword").with_slot("head", "cap")
    assert worn.slots == (("head", "cap"), ("weapon", "sword"))
    assert worn.with_slot("weapon", "axe").in_slot("weapon") == "axe"
    assert worn.equipped_items() == ("cap", "sword")


@pytest.mark.parametrize(("op", "value"), [("sub", 1), ("mul", -50)])
def test_a_modifier_rejects_unknown_ops_and_negative_percentages(
    op: str, value: int
) -> None:
    with pytest.raises(ValueError):
        StatModifier(stat="atk", op=op, value=value)


def test_an_actor_reads_its_base_stats_with_zero_as_default() -> None:
    actor = Actor(name="Wren", hp=1, max_hp=1, base_stats=(("atk", 5),))
    assert (actor.base_stat("atk"), actor.base_stat("def")) == (5, 0)


def _with_potion(state: WorldState) -> WorldState:
    from glyphwright.world.entities import Consumable, Item

    potion = Entity(
        id="potion",
        position=Position(at=ROOM.pos(2, 1)),
        item=Item(name="Potion"),
        consumable=Consumable(heal=3),
    )
    return state.with_entity(potion)


def test_taking_moves_the_item_into_the_inventory(state: WorldState) -> None:
    from glyphwright.kernel.events import ItemAcquired

    state = _with_potion(state)
    taken = fold(
        state, (ItemAcquired(actor=PLAYER, item="potion", origin=ROOM.pos(2, 1)),)
    )
    assert taken.entity("potion").at() is None
    assert taken.entity(PLAYER).carries() == ("potion",)


def test_using_destroys_the_item_and_clears_its_slot(state: WorldState) -> None:
    from glyphwright.kernel.events import ItemAcquired, ItemEquipped, ItemUsed

    state = fold(
        _with_potion(state),
        (
            ItemAcquired(actor=PLAYER, item="potion", origin=ROOM.pos(2, 1)),
            ItemEquipped(actor=PLAYER, item="potion", slot="belt"),
        ),
    )
    used = fold(state, (ItemUsed(actor=PLAYER, item="potion", target=PLAYER),))
    assert "potion" not in used.entities
    assert used.entity(PLAYER).carries() == ()
    assert used.entity(PLAYER).equipment == Equipment()


def test_healing_is_clamped_to_both_bounds(state: WorldState) -> None:
    from glyphwright.kernel.events import Healed

    # v0 finding K5: a negative amount drove hp below zero.
    assert fold(state, (Healed(target=PLAYER, amount=-50, source="x"),)).entity(
        PLAYER
    ).actor == Actor(name="Player", hp=0, max_hp=5)
    assert fold(state, (Healed(target=PLAYER, amount=99, source="x"),)).entity(
        PLAYER
    ).actor == Actor(name="Player", hp=5, max_hp=5)


def test_healing_something_that_is_not_an_actor_is_a_hard_error(
    state: WorldState,
) -> None:
    from glyphwright.kernel.events import Healed

    with pytest.raises(ValueError, match="not an actor"):
        fold(_with_potion(state), (Healed(target="potion", amount=1, source="x"),))
