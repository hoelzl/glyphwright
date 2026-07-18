"""The GUI's scene layer: ``compose`` is a pure function of the frame, and the
Scene — not the pixels — is the evidence (design 0011 §3, §5).

Nothing here imports pygame: scene composition must stay verifiable with the
``gui`` extra absent, which is what the bare CI job proves.
"""

from __future__ import annotations

from glyphwright.api import Engine
from glyphwright.content.pack import reference_pack
from glyphwright.frames.frame import DialogueView, GridView, LockView, flatten
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
    assert _rows(composed) == [row.rstrip() for row in flatten(frame.viewport)]
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


def _stack_at(composed: scene.Scene, x: int, y: int) -> list[str]:
    """The layered glyphs composed at one grid position, bottom to top."""
    return [cell.glyph for cell in composed.cells if (cell.x, cell.y) == (x, y)]


def test_the_ground_persists_under_an_actor() -> None:
    """The compositing defect 0012 §4 fixes: an occupied cell composes the
    ground glyph *and* the actor glyph, ground first, so the painter draws
    the floor under the player rather than replacing it."""
    frame = _engine().frame()
    composed = scene.compose(frame, ())
    player = next(cell for cell in composed.cells if cell.glyph == "@")
    assert _stack_at(composed, player.x, player.y) == [
        ".",
        "@",
    ], "the floor must be drawn beneath the player"


def test_an_occupied_fixture_cell_keeps_all_three_layers() -> None:
    engine = _engine()
    engine.step(Move("east"))
    engine.step(Move("east"))  # (3,1): onto the potion
    frame = engine.frame()
    composed = scene.compose(frame, ())
    player = next(cell for cell in composed.cells if cell.glyph == "@")
    assert _stack_at(composed, player.x, player.y) == [".", "!", "@"]


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


# -- click targets: the mouse can never say what the grammar cannot (13C) -----


def _target_commands(composed: scene.Scene) -> list[object]:
    return [target.command for target in composed.targets]


def test_grid_frames_offer_adjacent_cells_as_move_targets() -> None:
    frame = _engine().frame()  # at (1,1): north is a wall, but advertised?
    composed = scene.compose(frame, ())
    commands = _target_commands(composed)
    domain = frame.commands.domains("move")[0]
    for token in ("north", "south", "east", "west"):
        assert (Move(token) in commands) == (token in domain)


def test_every_move_token_gets_an_exit_slot_target() -> None:
    engine = _engine()
    for _ in range(6):
        engine.step(Move("east"))  # the inn door: east, enter, south, west
    frame = engine.frame()
    composed = scene.compose(frame, ())
    commands = _target_commands(composed)
    for token in frame.commands.domains("move")[0]:
        assert Move(token) in commands


def test_dialogue_choices_are_click_targets() -> None:
    from glyphwright.kernel.commands import Choose, Talk

    engine = Engine.new(reference_pack(), seed=23)
    for _ in range(6):
        engine.step(Move("east"))
    engine.step(Move("enter"))
    frame = engine.step(Talk("innkeeper")).frame
    composed = scene.compose(frame, ())
    commands = _target_commands(composed)
    assert isinstance(frame.viewport, DialogueView)
    for index in range(len(frame.viewport.choices)):
        assert Choose(str(index + 1)) in commands


def test_battle_rows_are_attack_targets_for_foes_only() -> None:
    from glyphwright.kernel.commands import Attack

    engine = _engine()
    frame = engine.step(Move("south")).frame
    composed = scene.compose(frame, ())
    commands = _target_commands(composed)
    assert Attack("bandit-1") in commands
    assert Attack("player") not in commands


def test_lock_frames_offer_the_pins_as_a_pick_target() -> None:
    from glyphwright.kernel.commands import Open, Pick

    engine = Engine.new(reference_pack(), seed=99)
    for _ in range(6):
        engine.step(Move("east"))
    engine.step(Move("enter"))
    engine.step(Move("down"))
    frame = engine.step(Open("strongbox")).frame
    composed = scene.compose(frame, ())
    assert Pick() in _target_commands(composed)


def test_click_dispatch_is_pure_geometry() -> None:
    frame = _engine().frame()
    composed = scene.compose(frame, ())
    target = next(t for t in composed.targets if t.command == Move("east"))
    inside = (target.x + target.w // 2, target.y + target.h // 2)
    assert scene.click(composed, inside) == Move("east")
    assert scene.click(composed, (0, 0)) is None


def test_targets_never_leak_into_golden_evidence() -> None:
    frame = _engine().frame()
    with_targets = scene.compose(frame, ())
    assert with_targets.targets
    assert "Move" not in scene.scene_text(with_targets)


# -- the golden serialization -------------------------------------------------


def test_scene_text_is_deterministic_and_names_the_regions() -> None:
    engine = _engine()
    frame = engine.step(Move("east")).frame
    composed = scene.compose(frame, frame.messages)
    dump = scene.scene_text(composed)
    assert dump == scene.scene_text(scene.compose(frame, frame.messages))
    assert "turn 1" in dump
    assert "village" in dump
