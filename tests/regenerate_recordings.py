"""The pinned recording: a tour of the reference world that must replay.

The tour takes and equips items, fights a battle to its end, flees another,
and crosses the portal down to the warren. Replaying it is the tripwire of
decision 0003: when a change alters what these commands produce, the pin
test fails. If the change is deliberate, bump ``RULES`` in
``src/glyphwright/harness/fingerprint.py``, then re-record and commit::

    uv run python tests/regenerate_recordings.py
"""

from __future__ import annotations

import io
from pathlib import Path

from glyphwright.api import Engine, reference_pack
from glyphwright.harness.recording import RecordingEngine
from glyphwright.kernel.commands import Attack, Command, Equip, Flee, Move, Take, Use
from glyphwright.kernel.state import MODE_BATTLE

PIN = Path(__file__).resolve().parent / "recordings" / "reference-tour.jsonl"
REGENERATE = "uv run python tests/regenerate_recordings.py"
SEED = 2026

_TO_THE_ITEMS: tuple[Command, ...] = (
    Move("east"),
    Move("east"),
    Take("potion-minor"),
    *(Move("east"),) * 3,
    *(Move("south"),) * 2,
    Take("iron-sword"),
    Equip("iron-sword"),
)
# From the sword, west along the bottom row until the goblin is in reach.
_TO_THE_GOBLIN: tuple[Command, ...] = (Move("west"),) * 3
_TO_THE_WARREN: tuple[Command, ...] = (*(Move("east"),) * 4, Move("down"))


def _step(engine: Engine, command: Command) -> None:
    result = engine.step(command)
    assert result.rejection is None, (command, result.rejection)


def _fight(engine: Engine) -> None:
    """Attack until the battle ends, drinking the potion when hurt."""
    while engine.frame().mode == MODE_BATTLE:
        frame = engine.frame()
        player = next(actor for actor in frame.actors if actor.id == "player")
        if "use" in frame.commands.verb_names() and player.hp <= player.max_hp // 2:
            _step(engine, Use(frame.commands.domains("use")[0][0]))
        else:
            _step(engine, Attack(frame.commands.domains("attack")[0][0]))


def tour(engine: Engine) -> None:
    """Drive the tour; every command must be accepted."""
    for command in _TO_THE_ITEMS + _TO_THE_GOBLIN:
        _step(engine, command)
    assert engine.frame().mode == MODE_BATTLE, "the walk west meets the goblin"
    _fight(engine)
    assert not engine._state.defeated, "the tour must survive its battle"
    for command in _TO_THE_WARREN:
        _step(engine, command)
    _step(engine, Move("east"))
    assert engine.frame().mode == MODE_BATTLE, "the marauder waits in the warren"
    _step(engine, Flee())


def render() -> str:
    """The pinned recording's text, recorded fresh."""
    sink = io.StringIO()
    tour(RecordingEngine.recording(reference_pack(), seed=SEED, sink=sink))
    return sink.getvalue()


if __name__ == "__main__":
    PIN.parent.mkdir(exist_ok=True)
    PIN.write_text(render(), encoding="utf-8", newline="\n")
    print(f"wrote {PIN.relative_to(PIN.parent.parent.parent).as_posix()}")
