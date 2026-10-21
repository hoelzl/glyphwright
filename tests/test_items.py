"""Taking, using, and equipping items, and what the grammar offers."""

from __future__ import annotations

import pytest

from glyphwright.api import Engine
from glyphwright.content.pack import ContentPack
from glyphwright.kernel.commands import Equip, Move, Take, Use
from glyphwright.kernel.events import (
    Healed,
    ItemAcquired,
    ItemEquipped,
    ItemUsed,
    TurnAdvanced,
)
from glyphwright.kernel.state import PLAYER
from glyphwright.world.entities import (
    Actor,
    Consumable,
    Entity,
    Equippable,
    Item,
    Position,
    StatModifier,
)
from glyphwright.world.grid import GridSpace

ROOM = GridSpace.from_text("room", "#####\n#...#\n#####")


def _engine(hp: int = 5) -> Engine:
    player = Entity(
        id=PLAYER,
        position=Position(at=ROOM.pos(1, 1)),
        actor=Actor(name="Wren", hp=hp, max_hp=10, base_stats=(("atk", 5),)),
    )
    potion = Entity(
        id="potion",
        position=Position(at=ROOM.pos(1, 1)),
        item=Item(name="Potion"),
        consumable=Consumable(heal=8),
    )
    sword = Entity(
        id="sword",
        position=Position(at=ROOM.pos(2, 1)),
        item=Item(name="Sword"),
        equippable=Equippable(
            slot="weapon", modifiers=(StatModifier(stat="atk", op="add", value=3),)
        ),
    )
    axe = Entity(
        id="axe",
        position=Position(at=ROOM.pos(2, 1)),
        item=Item(name="Axe"),
        equippable=Equippable(slot="weapon"),
    )
    pack = ContentPack(
        name="items", areas=(ROOM,), entities=(player, potion, sword, axe)
    )
    return Engine.new(pack, seed=1)


def _verbs(engine: Engine) -> tuple[str, ...]:
    return engine.frame().commands.verb_names()


def test_an_item_underfoot_is_offered_to_take() -> None:
    engine = _engine()
    assert engine.frame().commands.domains("take") == (("potion",),)


def test_taking_puts_the_item_in_the_inventory() -> None:
    engine = _engine()
    result = engine.step(Take("potion"))
    assert [type(event) for event in result.events] == [ItemAcquired, TurnAdvanced]
    assert engine._state.entity(PLAYER).carries() == ("potion",)
    assert "take" not in _verbs(engine)
    assert result.frame.messages == ("You take potion.",)


def test_using_a_potion_heals_what_actually_lands() -> None:
    engine = _engine(hp=5)
    engine.step(Take("potion"))
    result = engine.step(Use("potion"))
    assert [type(event) for event in result.events] == [ItemUsed, Healed, TurnAdvanced]
    healed = result.events[1]
    assert isinstance(healed, Healed) and healed.amount == 5
    assert engine._state.entity(PLAYER).actor == Actor(
        name="Wren", hp=10, max_hp=10, base_stats=(("atk", 5),)
    )
    assert "potion" not in engine._state.entities


def test_use_is_not_offered_at_full_health() -> None:
    engine = _engine(hp=10)
    engine.step(Take("potion"))
    assert "use" not in _verbs(engine)
    rejection = engine.step(Use("potion")).rejection
    assert rejection is not None
    # v2 finding N11: v0 said "you are carrying nothing usable".
    assert (rejection.reason, rejection.hint) == (
        "not_usable",
        "nothing you carry would have an effect now",
    )


def test_equipping_fills_the_slot_and_swapping_reports_the_old_item() -> None:
    engine = _engine()
    engine.step(Move("east"))
    engine.step(Take("axe"))
    engine.step(Take("sword"))
    assert engine.frame().commands.domains("equip") == (("axe", "sword"),)
    first = engine.step(Equip("axe")).events[0]
    assert first == ItemEquipped(actor=PLAYER, item="axe", slot="weapon")
    second = engine.step(Equip("sword"))
    assert second.events[0] == ItemEquipped(
        actor=PLAYER, item="sword", slot="weapon", replaced="axe"
    )
    assert second.frame.messages == ("You equip sword, putting away axe.",)
    assert engine.frame().commands.domains("equip") == (("axe",),)


def test_a_worn_item_is_still_carried() -> None:
    engine = _engine()
    engine.step(Move("east"))
    engine.step(Take("sword"))
    engine.step(Equip("sword"))
    player = engine._state.entity(PLAYER)
    assert "sword" in player.carries()
    assert player.equipment is not None
    assert player.equipment.in_slot("weapon") == "sword"


@pytest.mark.parametrize(
    ("command", "reason", "hint"),
    [
        (Take("sword"), "not_here", "you can take: potion"),
        (Equip("sword"), "not_equippable", "you are carrying nothing to equip"),
    ],
)
def test_item_commands_out_of_reach_are_rejected_in_their_own_words(
    command: Take | Equip, reason: str, hint: str
) -> None:
    rejection = _engine().step(command).rejection
    assert rejection is not None
    assert (rejection.reason, rejection.hint) == (reason, hint)


def test_every_frame_lists_what_the_player_carries() -> None:
    # v2 finding N13: v0's frames never said what the player carries.
    from glyphwright.frames.frame import ItemSummary

    engine = _engine()
    assert engine.frame().inventory == ()
    engine.step(Take("potion"))
    engine.step(Move("east"))
    engine.step(Take("sword"))
    frame = engine.step(Equip("sword")).frame
    assert frame.inventory == (
        ItemSummary(id="potion", name="Potion"),
        ItemSummary(id="sword", name="Sword", slot="weapon"),
    )


def test_the_inventory_is_on_the_wire_and_in_the_transcript() -> None:
    from jsonschema import Draft202012Validator

    from glyphwright.frontends import plain
    from glyphwright.frontends.wire import encode_frame
    from glyphwright.harness.schema import frame_schema

    engine = _engine()
    engine.step(Take("potion"))
    engine.step(Move("east"))
    engine.step(Take("sword"))
    frame = engine.step(Equip("sword")).frame
    encoded = encode_frame(frame)
    Draft202012Validator(frame_schema()).validate(encoded)
    assert encoded["inventory"] == [
        {"id": "potion", "name": "Potion"},
        {"id": "sword", "name": "Sword", "slot": "weapon"},
    ]
    text = plain.render(frame)
    assert text.splitlines()[-2] == "[carrying potion, sword (weapon)]"
    assert plain.parse(text) == plain.project(frame)
