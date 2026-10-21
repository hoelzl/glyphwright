"""The menu viewport: a battle's frame names the combatants, not a map."""

from __future__ import annotations

from jsonschema import Draft202012Validator

from glyphwright.frames.frame import (
    ActorSummary,
    MenuView,
    PromptSpec,
    SemanticFrame,
)
from glyphwright.frontends import plain
from glyphwright.frontends.wire import encode_frame
from glyphwright.harness.schema import frame_schema
from glyphwright.kernel.commands import CommandGrammar
from glyphwright.kernel.state import PLAYER
from glyphwright.world.space import PosId

HOME = PosId.parse("village:1,2")
FRAME = SemanticFrame(
    turn=3,
    mode="battle",
    viewport=MenuView(area="village", combatants=("bandit-1", PLAYER)),
    actors=(
        ActorSummary(id="bandit-1", name="Bandit", hp=8, max_hp=8, at=HOME),
        ActorSummary(id=PLAYER, name="Wren", hp=15, max_hp=20, at=HOME),
    ),
    messages=("Battle is joined!", "bandit-1 hits you for 2 damage."),
    prompt=PromptSpec(),
    commands=CommandGrammar(verbs=(("attack", (("bandit-1",),)), ("flee", ()))),
)


def test_a_menu_frame_validates_on_the_wire() -> None:
    encoded = encode_frame(FRAME)
    Draft202012Validator(frame_schema()).validate(encoded)
    assert encoded["viewport"] == {
        "kind": "menu",
        "area": "village",
        "combatants": ["bandit-1", PLAYER],
    }


def test_the_plain_transcript_lists_the_initiative_instead_of_a_map() -> None:
    text = plain.render(FRAME)
    assert text.splitlines()[:2] == [
        "== turn 3 | battle | village ==",
        "[initiative bandit-1 8/8, player 15/20]",
    ]
    assert plain.parse(text) == plain.project(FRAME)
