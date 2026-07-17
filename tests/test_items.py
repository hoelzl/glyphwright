"""Inventory semantics: take, use, equip (design 0003 sections 8.1 and 18.2)."""

from __future__ import annotations

import pytest

from glyphwright.api import Engine
from glyphwright.content.pack import reference_pack
from glyphwright.kernel.commands import Equip, Move, Take, Use
from glyphwright.kernel.events import (
    Healed,
    ItemAcquired,
    ItemEquipped,
    ItemUsed,
    TurnAdvanced,
)
from glyphwright.kernel.state import PLAYER, fold


def _engine() -> Engine:
    return Engine.new(reference_pack(), seed=1)


def _at_potion() -> Engine:
    """Walk the player from the start onto the potion's tile."""
    engine = _engine()
    engine.step(Move("east"))
    engine.step(Move("east"))
    return engine


def _with_potion() -> Engine:
    engine = _at_potion()
    engine.step(Take("potion-minor"))
    return engine


def _with_sword() -> Engine:
    """Walk to the sword and pick it up."""
    engine = _with_potion()
    for token in ("east", "east", "east", "south", "south"):
        engine.step(Move(token))
    engine.step(Take("iron-sword"))
    return engine


# -- take ---------------------------------------------------------------------


def test_take_is_advertised_only_where_an_item_lies() -> None:
    engine = _engine()
    assert "take" not in engine.frame().commands.verb_names()
    engine = _at_potion()
    grammar = engine.frame().commands
    assert grammar.domains("take") == (("potion-minor",),)


def test_taking_moves_the_item_from_the_ground_to_the_inventory() -> None:
    engine = _at_potion()
    result = engine.step(Take("potion-minor"))
    assert result.accepted
    assert [type(event) for event in result.events] == [ItemAcquired, TurnAdvanced]
    state = engine._state
    assert state.entity("potion-minor").at() is None
    inventory = state.entity(PLAYER).inventory
    assert inventory is not None and "potion-minor" in inventory.items


def test_taking_spends_the_turn() -> None:
    engine = _at_potion()
    before = engine.frame().turn
    engine.step(Take("potion-minor"))
    assert engine.frame().turn == before + 1


def test_a_taken_item_disappears_from_the_map() -> None:
    engine = _engine()
    assert any("!" in row for row in engine.frame().viewport.tiles)
    engine = _at_potion()
    engine.step(Take("potion-minor"))
    # Step off the tile: the glyph must be gone because the item is carried,
    # not merely because the player is standing on top of it.
    frame = engine.step(Move("west")).frame
    assert not any("!" in row for row in frame.viewport.tiles)


def test_taking_what_is_not_here_is_rejected_without_a_turn() -> None:
    engine = _engine()
    result = engine.step(Take("potion-minor"))
    assert result.rejection is not None
    assert result.rejection.reason == "not_here"
    assert engine.frame().turn == 0


# -- use ----------------------------------------------------------------------


def test_using_a_potion_heals_up_to_the_maximum() -> None:
    engine = _with_potion()
    result = engine.step(Use("potion-minor"))
    assert result.accepted
    assert [type(event) for event in result.events] == [
        ItemUsed,
        Healed,
        TurnAdvanced,
    ]
    used, healed = result.events[0], result.events[1]
    assert isinstance(used, ItemUsed) and used.consumed
    # The pack starts the player at 17/20 and the potion heals 6: only 3 land.
    assert isinstance(healed, Healed) and healed.amount == 3
    actor = engine._state.entity(PLAYER).actor
    assert actor is not None and (actor.hp, actor.max_hp) == (20, 20)


def test_a_consumed_item_is_gone_from_the_world() -> None:
    engine = _with_potion()
    engine.step(Use("potion-minor"))
    state = engine._state
    assert "potion-minor" not in state.entities
    inventory = state.entity(PLAYER).inventory
    assert inventory is not None and "potion-minor" not in inventory.items


def test_using_what_is_not_carried_is_rejected() -> None:
    engine = _engine()
    result = engine.step(Use("potion-minor"))
    assert result.rejection is not None
    assert result.rejection.reason == "not_usable"
    assert engine.frame().turn == 0


def test_use_is_advertised_only_while_a_consumable_is_carried() -> None:
    engine = _with_potion()
    assert engine.frame().commands.domains("use") == (("potion-minor",),)
    engine.step(Use("potion-minor"))
    assert "use" not in engine.frame().commands.verb_names()


# -- equip --------------------------------------------------------------------


def test_equipping_fills_the_slot_and_reports_no_replacement() -> None:
    engine = _with_sword()
    result = engine.step(Equip("iron-sword"))
    assert result.accepted
    equipped = result.events[0]
    assert isinstance(equipped, ItemEquipped)
    assert (equipped.slot, equipped.replaced) == ("weapon", None)
    equipment = engine._state.entity(PLAYER).equipment
    assert equipment is not None and dict(equipment.slots) == {"weapon": "iron-sword"}


def test_an_equipped_item_leaves_the_equip_domain() -> None:
    engine = _with_sword()
    assert engine.frame().commands.domains("equip") == (("iron-sword",),)
    engine.step(Equip("iron-sword"))
    assert "equip" not in engine.frame().commands.verb_names()


def test_equipping_what_is_not_carried_is_rejected() -> None:
    engine = _engine()
    result = engine.step(Equip("iron-sword"))
    assert result.rejection is not None
    assert result.rejection.reason == "not_equippable"
    assert engine.frame().turn == 0


# -- fold equivalence ---------------------------------------------------------


@pytest.mark.parametrize(
    "prepare, command",
    [
        (_at_potion, Take("potion-minor")),
        (_with_potion, Use("potion-minor")),
        (_with_sword, Equip("iron-sword")),
    ],
)
def test_item_events_fold_to_the_successor_state(prepare, command) -> None:  # type: ignore[no-untyped-def]
    engine = prepare()
    before = engine._state
    result = engine.step(command)
    folded = fold(before, result.events)
    after = engine._state
    assert folded.entities == after.entities
    assert folded.turn == after.turn


def test_item_messages_are_rendered_from_events() -> None:
    engine = _at_potion()
    frame = engine.step(Take("potion-minor")).frame
    assert "You take potion-minor." in frame.messages


def test_the_player_is_drawn_above_an_item_on_the_same_tile() -> None:
    # "potion-minor" sorts after "player"; the actor must still win the tile.
    engine = _at_potion()
    tiles = engine.frame().viewport.tiles
    assert any("@" in row for row in tiles), "the player may never vanish"
    assert not any("!" in row for row in tiles), "the potion is underfoot"


def test_use_is_not_advertised_when_it_would_do_nothing() -> None:
    import dataclasses

    engine = _with_potion()
    player = engine._state.entity("player")
    assert player.actor is not None
    healed = dataclasses.replace(player, actor=dataclasses.replace(player.actor, hp=20))
    engine._state = engine._state.with_entity(healed)
    assert "use" not in engine.frame().commands.verb_names()
    result = engine.step(Use("potion-minor"))
    assert result.rejection is not None, "a no-effect use must not waste the item"
    assert "potion-minor" in engine._state.entities
