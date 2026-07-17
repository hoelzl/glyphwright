"""The stat pipeline: base -> additive -> multiplicative -> clamps, with
provenance on every contribution (design 0003 section 9.1)."""

from __future__ import annotations

from glyphwright.api import Engine
from glyphwright.content.pack import reference_pack
from glyphwright.effects.stats import derive
from glyphwright.kernel.state import PLAYER, WorldState
from glyphwright.world.entities import (
    Actor,
    Entity,
    Equipment,
    Equippable,
    Inventory,
    Item,
    StatModifier,
)


def _state_with(*entities: Entity) -> WorldState:
    base = Engine.new(reference_pack(), seed=1)._state
    for entity in entities:
        base = base.with_entity(entity)
    return base


def _hero(**kwargs: object) -> Entity:
    defaults: dict[str, object] = {
        "id": "hero",
        "actor": Actor(name="Hero", hp=10, max_hp=10, base_stats=(("atk", 5),)),
    }
    defaults.update(kwargs)
    return Entity(**defaults)  # type: ignore[arg-type]


def _blade(*modifiers: StatModifier) -> Entity:
    return Entity(
        id="blade",
        item=Item(name="Blade"),
        equippable=Equippable(slot="weapon", modifiers=tuple(modifiers)),
    )


def test_an_unmodified_stat_is_its_base_value() -> None:
    state = _state_with(_hero())
    derivation = derive(state, "hero", "atk")
    assert derivation.value == 5
    assert [c.op for c in derivation.contributions] == ["base"]


def test_a_missing_stat_derives_to_zero() -> None:
    state = _state_with(_hero())
    assert derive(state, "hero", "luck").value == 0


def test_equipment_contributes_additively_with_provenance() -> None:
    state = _state_with(
        _blade(StatModifier(stat="atk", op="add", value=3)),
        _hero(
            inventory=Inventory(items=("blade",)),
            equipment=Equipment(slots=(("weapon", "blade"),)),
        ),
    )
    derivation = derive(state, "hero", "atk")
    assert derivation.value == 8
    contribution = derivation.contributions[1]
    assert contribution.op == "add"
    assert "blade" in contribution.source
    assert contribution.running == 8


def test_multiplicative_applies_after_all_additive() -> None:
    state = _state_with(
        _blade(
            StatModifier(stat="atk", op="mul", value=200),
            StatModifier(stat="atk", op="add", value=3),
        ),
        _hero(
            inventory=Inventory(items=("blade",)),
            equipment=Equipment(slots=(("weapon", "blade"),)),
        ),
    )
    # (5 + 3) * 200% = 16 — never (5 * 2) + 3.
    assert derive(state, "hero", "atk").value == 16


def test_the_result_clamps_at_zero() -> None:
    state = _state_with(
        _blade(StatModifier(stat="atk", op="add", value=-99)),
        _hero(
            inventory=Inventory(items=("blade",)),
            equipment=Equipment(slots=(("weapon", "blade"),)),
        ),
    )
    derivation = derive(state, "hero", "atk")
    assert derivation.value == 0
    assert derivation.contributions[-1].op == "clamp"


def test_unequipped_items_do_not_contribute() -> None:
    state = _state_with(
        _blade(StatModifier(stat="atk", op="add", value=3)),
        _hero(inventory=Inventory(items=("blade",))),
    )
    assert derive(state, "hero", "atk").value == 5


def test_a_modifier_with_an_unknown_op_is_unrepresentable() -> None:
    import pytest

    with pytest.raises(ValueError, match="op"):
        StatModifier(stat="atk", op="multiply", value=150)


def test_equipping_the_reference_sword_raises_atk() -> None:
    from glyphwright.kernel.commands import Equip, Move, Take

    engine = Engine.new(reference_pack(), seed=1)
    for token in ("east", "east", "east", "east", "east", "south", "south"):
        engine.step(Move(token))
    engine.step(Take("iron-sword"))
    assert derive(engine._state, PLAYER, "atk").value == 5
    engine.step(Equip("iron-sword"))
    assert derive(engine._state, PLAYER, "atk").value == 8
