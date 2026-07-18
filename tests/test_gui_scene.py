"""The GUI's scene layer: ``compose`` is a pure function of the frame, and the
Scene — not the pixels — is the evidence (design 0011 §3, §5).

Nothing here imports pygame: scene composition must stay verifiable with the
``gui`` extra absent, which is what the bare CI job proves.
"""

from __future__ import annotations

from glyphwright.api import Engine
from glyphwright.content.pack import reference_pack
from glyphwright.frames.frame import DialogueView, GridView, LockView
from glyphwright.frontends import plain
from glyphwright.frontends.gui import scene
from glyphwright.kernel.commands import Move


def _engine() -> Engine:
    return Engine.new(reference_pack(), seed=17)


def _rows(composed: scene.Scene) -> list[str]:
    """Reassemble the cell grid into glyph rows for comparison with tiles."""
    if not composed.cells:
        return []
    height = max(cell.y for cell in composed.cells) + 1
    width = max(cell.x for cell in composed.cells) + 1
    grid = [[" "] * width for _ in range(height)]
    for cell in composed.cells:
        grid[cell.y][cell.x] = cell.glyph
    return ["".join(row).rstrip() for row in grid]


# -- purity and determinism ---------------------------------------------------


def test_compose_is_pure_and_deterministic() -> None:
    frame = _engine().frame()
    log = ("You wake.",)
    assert scene.compose(frame, log) == scene.compose(frame, log)


# -- grid frames --------------------------------------------------------------


def test_grid_frames_compose_to_cells_matching_the_tiles() -> None:
    engine = _engine()
    frame = engine.step(Move("east")).frame
    composed = scene.compose(frame, frame.messages)
    assert isinstance(frame.viewport, GridView)
    assert _rows(composed) == [row.rstrip() for row in frame.viewport.tiles]
    assert composed.text == ()


def test_every_cell_carries_a_palette_color() -> None:
    frame = _engine().frame()
    composed = scene.compose(frame, ())
    for cell in composed.cells:
        assert len(cell.fg) == 3
        assert all(0 <= channel <= 255 for channel in cell.fg)
    player = [cell for cell in composed.cells if cell.glyph == "@"]
    wall = [cell for cell in composed.cells if cell.glyph == "#"]
    assert player and wall
    assert player[0].fg != wall[0].fg, "the player must stand out from walls"


# -- room frames --------------------------------------------------------------


def test_room_frames_compose_to_prose() -> None:
    engine = _engine()
    for _ in range(6):
        engine.step(Move("east"))
    frame = engine.step(Move("enter")).frame
    composed = scene.compose(frame, ())
    assert composed.cells == ()
    assert any("The Gilded Tankard" in line for line in composed.text)
    assert composed.exits, "a room's exits must stay actionable"


# -- battle, dialogue, and lock frames (13B: full parity) ---------------------


def test_battle_frames_compose_to_the_combatant_list() -> None:
    engine = _engine()
    frame = engine.step(Move("south")).frame  # the bandit engages
    composed = scene.compose(frame, frame.messages)
    assert composed.mode == "battle"
    assert any("battle" in line for line in composed.text)
    for actor in frame.actors:
        assert any(
            actor.id in line and f"{actor.hp}/{actor.max_hp}" in line
            for line in composed.text
        )


def test_dialogue_frames_compose_to_speaker_text_and_choices() -> None:
    from glyphwright.kernel.commands import Talk

    engine = Engine.new(reference_pack(), seed=23)
    for _ in range(6):
        engine.step(Move("east"))
    engine.step(Move("enter"))
    frame = engine.step(Talk("innkeeper")).frame
    composed = scene.compose(frame, frame.messages)
    assert composed.mode == "dialogue"
    rejoined = " ".join(composed.text)
    assert isinstance(frame.viewport, DialogueView)
    assert frame.viewport.speaker in rejoined
    assert frame.viewport.text in rejoined
    for index, choice in enumerate(frame.viewport.choices):
        assert any(
            line.strip().startswith(f"{index + 1})") and choice in line
            for line in composed.text
        )


def test_lock_frames_compose_to_the_pin_display() -> None:
    from glyphwright.kernel.commands import Open

    engine = Engine.new(reference_pack(), seed=99)
    for _ in range(6):
        engine.step(Move("east"))
    engine.step(Move("enter"))
    engine.step(Move("down"))
    frame = engine.step(Open("strongbox")).frame
    composed = scene.compose(frame, frame.messages)
    assert composed.mode == "minigame:lockpick"
    assert isinstance(frame.viewport, LockView)
    rejoined = " ".join(composed.text)
    assert frame.viewport.target in rejoined
    assert f"{frame.viewport.pins}/{frame.viewport.total}" in rejoined


# -- the typed bar is echoed through the scene --------------------------------


def test_the_bar_appears_in_the_scene_only_while_typing() -> None:
    frame = _engine().frame()
    assert scene.compose(frame, ()).bar is None
    composed = scene.compose(frame, (), bar="> move ea")
    assert composed.bar == "> move ea"
    # The bar is transient input echo, never golden evidence.
    assert "move ea" not in scene.scene_text(scene.compose(frame, ()))


# -- projection consistency against plain (0011 §5.2) -------------------------


def test_the_scene_shows_everything_plain_commits_to() -> None:
    from glyphwright.kernel.commands import Open, Talk

    engine = _engine()
    frames = [engine.frame()]
    for token in ("east", "east", "west"):
        frames.append(engine.step(Move(token)).frame)
    frames.append(engine.step(Move("south")).frame)  # a battle frame
    engine = Engine.new(reference_pack(), seed=23)
    for _ in range(6):
        engine.step(Move("east"))
    frames.append(engine.step(Move("enter")).frame)  # a room frame
    frames.append(engine.step(Talk("innkeeper")).frame)  # a dialogue frame
    engine = Engine.new(reference_pack(), seed=99)
    for _ in range(6):
        engine.step(Move("east"))
    engine.step(Move("enter"))
    engine.step(Move("down"))
    frames.append(engine.step(Open("strongbox")).frame)  # a lock frame

    for frame in frames:
        projection = plain.project(frame)
        composed = scene.compose(frame, frame.messages)
        assert composed.turn == projection.turn
        assert composed.mode == projection.mode
        assert composed.area == projection.area
        rows = _rows(composed)
        for tile_row in projection.tiles:
            assert tile_row.rstrip() in rows
        for message in projection.messages:
            assert message in composed.log
        # Compose wraps prose at TEXT_COLS; rejoining the wrapped lines must
        # give back every fact plain commits to, with nothing dropped.
        rejoined = " ".join(composed.text)
        for prose in projection.room:
            assert prose in rejoined
        if projection.hp is not None:
            assert f"hp {projection.hp[0]}/{projection.hp[1]}" in composed.status
        if projection.mp is not None:
            assert f"mp {projection.mp[0]}/{projection.mp[1]}" in composed.status
        for combatant in projection.combatants:
            name, hp = combatant.split(" ")
            assert any(name in line and hp in line for line in composed.text)
        for entry in projection.dialogue:
            # "speaker: text" and "1. choice" lines: the facts must appear,
            # whatever numbering or wrapping the scene chose.
            fact = entry.split(". ", 1)[1] if entry[:1].isdigit() else entry
            assert fact in rejoined
        if projection.lock is not None:
            target, pins = projection.lock.removesuffix(" pins").split(": ")
            assert target in rejoined
            assert pins in rejoined


# -- the golden serialization -------------------------------------------------


def test_scene_text_is_deterministic_and_names_the_regions() -> None:
    engine = _engine()
    frame = engine.step(Move("east")).frame
    composed = scene.compose(frame, frame.messages)
    dump = scene.scene_text(composed)
    assert dump == scene.scene_text(scene.compose(frame, frame.messages))
    assert "turn 1" in dump
    assert "village" in dump
