"""The tactics arena: battle on a grid, movement and range reusing the
spatial model unchanged (design 0006 §2, 0003 §10.1)."""

from __future__ import annotations

from glyphwright.api import Engine
from glyphwright.content.pack import reference_pack
from glyphwright.frames.frame import GridView
from glyphwright.kernel.commands import Attack, Cast, Flee, Move
from glyphwright.kernel.events import ModePopped, ModePushed, Moved
from glyphwright.kernel.state import PLAYER, fold


def _engine() -> Engine:
    return Engine.new(reference_pack(), seed=67)


def _at_warren() -> Engine:
    """Walk to the warren: east along row 1, south to (7,3), down the hole."""
    engine = _engine()
    for _ in range(6):
        engine.step(Move("east"))
    engine.step(Move("south"))
    engine.step(Move("south"))
    engine.step(Move("down"))
    return engine


def _engaged() -> Engine:
    """Step up to the marauder: the battle opens in the pit."""
    engine = _at_warren()
    engine.step(Move("east"))
    return engine


# -- entering the arena -------------------------------------------------------


def test_a_tactics_engagement_moves_everyone_into_the_arena() -> None:
    engine = _at_warren()
    result = engine.step(Move("east"))
    pushes = [e for e in result.events if isinstance(e, ModePushed)]
    assert pushes and pushes[0].mode == "battle"
    assert dict(pushes[0].returns), "the push must carry the way home"
    player_at = engine._state.entity(PLAYER).at()
    assert player_at is not None and player_at.area == "pit"
    marauder_at = engine._state.entity("marauder-1").at()
    assert marauder_at is not None and marauder_at.area == "pit"
    assert engine._state.mode == "battle"
    assert engine._state.battle_returns


def test_placement_is_deterministic_and_disjoint() -> None:
    first = _engaged()._state
    second = _engaged()._state
    assert first.entity(PLAYER).at() == second.entity(PLAYER).at()
    assert first.entity(PLAYER).at() != first.entity("marauder-1").at()


def test_the_arena_frame_is_a_grid() -> None:
    engine = _engaged()
    frame = engine.frame()
    assert frame.mode == "battle"
    assert isinstance(frame.viewport, GridView)
    assert frame.viewport.area == "pit"
    verbs = set(frame.commands.verb_names())
    assert {"move", "flee", "look"} <= verbs
    assert "wait" not in verbs


def test_attack_needs_melee_adjacency_on_the_grid() -> None:
    engine = _engaged()
    state = engine._state
    player_at = state.entity(PLAYER).at()
    marauder_at = state.entity("marauder-1").at()
    assert player_at is not None and marauder_at is not None
    space = state.areas["pit"]
    adjacent = space.melee_range(player_at, marauder_at)
    has_attack = "attack" in engine.frame().commands.verb_names()
    assert adjacent == has_attack, "the grammar mirrors grid adjacency"


def test_cast_reaches_across_the_arena() -> None:
    """Magic outranges steel: with every foe out of melee reach, attack is
    gone from the grammar but a foe-targeting cast still resolves."""
    import dataclasses

    from glyphwright.world.entities import Position

    engine = _engaged()
    state = engine._state
    space = state.areas["pit"]
    marauder_at = state.entity("marauder-1").at()
    assert marauder_at is not None
    far = next(
        pos
        for pos in space.positions()
        if space.blocked_reason(state, pos, PLAYER) is None
        and not space.melee_range(pos, marauder_at)
    )
    player = state.entity(PLAYER)
    engine._state = state.with_entity(
        dataclasses.replace(player, position=Position(at=far))
    )
    grammar = engine.frame().commands
    assert "attack" not in grammar.verb_names(), "steel needs adjacency"
    assert "marauder-1" in grammar.domains("cast")[1], "magic outranges steel"
    result = engine.step(Cast("firebolt", "marauder-1"))
    assert result.accepted


def test_foes_chase_across_the_arena() -> None:
    engine = _engaged()
    state = engine._state
    marauder_before = state.entity("marauder-1").at()
    result = engine.step(Move("east"))
    assert "marauder-1" in engine._state.entities, "a move cannot kill"
    moved = [
        e for e in result.events if isinstance(e, Moved) and e.actor == "marauder-1"
    ]
    struck = any(getattr(e, "source", None) == "marauder-1" for e in result.events)
    assert moved or struck, "an arena foe closes or strikes each round"
    if moved:
        assert engine._state.entity("marauder-1").at() != marauder_before


# -- leaving the arena --------------------------------------------------------


def test_flee_returns_everyone_home() -> None:
    engine = _at_warren()
    origin = engine._state.entity(PLAYER).at()
    marauder_origin = engine._state.entity("marauder-1").at()
    engine.step(Move("east"))
    engaged_at = engine._state.entity(PLAYER).at()
    result = engine.step(Flee())
    assert result.accepted
    pops = [e for e in result.events if isinstance(e, ModePopped)]
    assert pops and pops[0].outcome == "fled"
    assert engine._state.mode == "exploration"
    assert engine._state.battle_returns == ()
    player_at = engine._state.entity(PLAYER).at()
    assert player_at is not None and player_at.area == "warren"
    assert player_at == engaged_at or player_at.area != "pit"
    # The homecoming event returned the marauder to its recorded origin; its
    # own chase turn in the same round may then move it again (aggro
    # persists by design) — but it must be back in the warren, not the pit.
    homecomings = [
        e
        for e in result.events
        if isinstance(e, Moved) and e.actor == "marauder-1" and e.exit == "return"
    ]
    assert homecomings and homecomings[0].destination == marauder_origin
    marauder_at = engine._state.entity("marauder-1").at()
    assert marauder_at is not None and marauder_at.area == "warren"
    assert origin is not None


def test_victory_returns_the_survivor_and_drops_the_dead() -> None:
    import dataclasses

    engine = _at_warren()
    player = engine._state.entity(PLAYER)
    assert player.actor is not None
    juggernaut = dataclasses.replace(
        player,
        actor=dataclasses.replace(
            player.actor, base_stats=(("atk", 40), ("def", 10), ("spd", 9))
        ),
    )
    engine._state = engine._state.with_entity(juggernaut)
    engine.step(Move("east"))
    for _ in range(30):
        if engine._state.mode != "battle":
            break
        frame = engine.frame()
        if "attack" in frame.commands.verb_names():
            engine.step(Attack("marauder-1"))
        else:
            domain = frame.commands.domains("move")[0]
            engine.step(Move(domain[0]))
    assert engine._state.mode == "exploration"
    assert "marauder-1" not in engine._state.entities
    player_at = engine._state.entity(PLAYER).at()
    assert player_at is not None and player_at.area == "warren", "the victor walks home"
    assert engine._state.battle_returns == ()


# -- determinism --------------------------------------------------------------


def test_arena_battles_fold_and_replay() -> None:
    engine = _at_warren()
    before = engine._state
    result = engine.step(Move("east"))
    assert fold(before, result.events) == engine._state

    def run() -> list[object]:
        e = Engine.new(reference_pack(), seed=71)
        for _ in range(6):
            e.step(Move("east"))
        e.step(Move("south"))
        e.step(Move("south"))
        e.step(Move("down"))
        e.step(Move("east"))
        return [e.step(Cast("firebolt", "marauder-1")).events for _ in range(3)]

    assert run() == run()


# -- content validation -------------------------------------------------------


def test_an_arena_reference_must_resolve_to_a_grid() -> None:
    import pathlib
    import tempfile

    import pytest

    from glyphwright.content.loader import PackError, load_pack

    with tempfile.TemporaryDirectory() as raw:
        root = pathlib.Path(raw)
        (root / "pack.toml").write_text('name = "bad"\n', encoding="utf-8")
        (root / "areas.toml").write_text(
            '[[grid]]\narea = "field"\nrows = """\n...\n"""\n', encoding="utf-8"
        )
        (root / "entities.toml").write_text(
            '[[entity]]\nid = "player"\nposition = "field:0,0"\n'
            "[entity.actor]\nname = 'P'\nhp = 5\nmax_hp = 5\n"
            '[[entity]]\nid = "brute"\nposition = "field:2,0"\n'
            "[entity.actor]\nname = 'B'\nhp = 5\nmax_hp = 5\n"
            '[entity.ai]\nhostile = true\nengages = true\narena = "nowhere"\n',
            encoding="utf-8",
        )
        with pytest.raises(PackError, match="arena"):
            load_pack(root)


def test_an_arena_with_a_portal_is_rejected() -> None:
    import pathlib
    import tempfile

    import pytest

    from glyphwright.content.loader import PackError, load_pack

    with tempfile.TemporaryDirectory() as raw:
        root = pathlib.Path(raw)
        (root / "pack.toml").write_text('name = "bad"\n', encoding="utf-8")
        (root / "areas.toml").write_text(
            '[[grid]]\narea = "field"\nrows = """\n...\n"""\n'
            '[[grid]]\narea = "ring"\nrows = """\n...\n"""\n',
            encoding="utf-8",
        )
        (root / "entities.toml").write_text(
            '[[entity]]\nid = "player"\nposition = "field:0,0"\n'
            "[entity.actor]\nname = 'P'\nhp = 5\nmax_hp = 5\n"
            '[[entity]]\nid = "brute"\nposition = "field:2,0"\n'
            "[entity.actor]\nname = 'B'\nhp = 5\nmax_hp = 5\n"
            '[entity.ai]\nhostile = true\nengages = true\narena = "ring"\n'
            '[[entity]]\nid = "backdoor"\nposition = "ring:0,0"\n'
            '[entity.portal]\ntoken = "out"\nto = "field:0,0"\n',
            encoding="utf-8",
        )
        with pytest.raises(PackError, match="portal"):
            load_pack(root)


def test_a_fov_arena_conceals_unseen_foes_everywhere_in_the_frame() -> None:
    """The one visible set rules the whole battle frame: an unseen foe is
    neither drawn, nor listed, nor narrated (design 0006 §1 applied to §2)."""
    import dataclasses
    import pathlib
    import tempfile

    from glyphwright.content.loader import load_pack
    from glyphwright.kernel.events import Moved as MovedEvent
    from glyphwright.modes import battle
    from glyphwright.world.entities import Position
    from glyphwright.world.grid import GridSpace

    with tempfile.TemporaryDirectory() as raw:
        root = pathlib.Path(raw)
        (root / "pack.toml").write_text('name = "fogring"\n', encoding="utf-8")
        (root / "areas.toml").write_text(
            '[[grid]]\narea = "field"\nrows = """\n....\n"""\n'
            '[[grid]]\narea = "ring"\nfov = 2\nrows = """\n'
            ".........\n.........\n.........\n"
            '"""\n',
            encoding="utf-8",
        )
        (root / "entities.toml").write_text(
            '[[entity]]\nid = "player"\nposition = "field:0,0"\n'
            "[entity.actor]\nname = 'P'\nhp = 20\nmax_hp = 20\n"
            "[entity.renderable]\nglyph = '@'\nlabel = 'you'\n"
            '[[entity]]\nid = "brute"\nposition = "field:2,0"\n'
            "[entity.actor]\nname = 'B'\nhp = 30\nmax_hp = 30\n"
            "[entity.renderable]\nglyph = 'B'\nlabel = 'brute'\n"
            '[entity.ai]\nhostile = true\nengages = true\narena = "ring"\n',
            encoding="utf-8",
        )
        pack = load_pack(root)
    engine = Engine.new(pack, seed=13)
    engine.step(Move("east"))
    state = engine._state
    assert state.mode == "battle" and state.battle_returns
    ring = state.areas["ring"]
    assert isinstance(ring, GridSpace)
    far = ring.pos(8, 2)
    brute = state.entity("brute")
    engine._state = state.with_entity(
        dataclasses.replace(brute, position=Position(at=far))
    )
    frame = engine.frame()
    assert isinstance(frame.viewport, GridView)
    assert frame.viewport.tiles[2][8] == "?", "beyond the light"
    listed = {actor.id for actor in frame.actors}
    assert PLAYER in listed and "brute" not in listed
    unseen_move = MovedEvent(
        actor="brute", origin=ring.pos(7, 2), destination=far, exit="east"
    )
    assert battle.view(engine._state, (unseen_move,)).messages == ()


def test_a_portal_may_not_claim_a_reserved_battle_token() -> None:
    import pathlib
    import tempfile

    import pytest

    from glyphwright.content.loader import PackError, load_pack

    with tempfile.TemporaryDirectory() as raw:
        root = pathlib.Path(raw)
        (root / "pack.toml").write_text('name = "bad"\n', encoding="utf-8")
        (root / "areas.toml").write_text(
            '[[grid]]\narea = "field"\nrows = """\n...\n"""\n', encoding="utf-8"
        )
        (root / "entities.toml").write_text(
            '[[entity]]\nid = "player"\nposition = "field:0,0"\n'
            "[entity.actor]\nname = 'P'\nhp = 5\nmax_hp = 5\n"
            '[[entity]]\nid = "trapdoor"\nposition = "field:2,0"\n'
            '[entity.portal]\ntoken = "return"\nto = "field:0,0"\n',
            encoding="utf-8",
        )
        with pytest.raises(PackError, match="reserved"):
            load_pack(root)


def test_an_arena_must_seat_the_possible_combatants() -> None:
    """Load-time capacity: the player plus every hostile in the engager's
    home area must fit, or the authored tactics content could silently
    degrade to a menu battle (design 0006 §2)."""
    import pathlib
    import tempfile

    import pytest

    from glyphwright.content.loader import PackError, load_pack

    with tempfile.TemporaryDirectory() as raw:
        root = pathlib.Path(raw)
        (root / "pack.toml").write_text('name = "bad"\n', encoding="utf-8")
        (root / "areas.toml").write_text(
            '[[grid]]\narea = "field"\nrows = """\n.....\n"""\n'
            '[[grid]]\narea = "ring"\nrows = """\n..\n"""\n',
            encoding="utf-8",
        )
        (root / "entities.toml").write_text(
            '[[entity]]\nid = "player"\nposition = "field:0,0"\n'
            "[entity.actor]\nname = 'P'\nhp = 5\nmax_hp = 5\n"
            '[[entity]]\nid = "brute"\nposition = "field:2,0"\n'
            "[entity.actor]\nname = 'B'\nhp = 5\nmax_hp = 5\n"
            '[entity.ai]\nhostile = true\nengages = true\narena = "ring"\n'
            '[[entity]]\nid = "thug"\nposition = "field:3,0"\n'
            "[entity.actor]\nname = 'T'\nhp = 5\nmax_hp = 5\n"
            "[entity.ai]\nhostile = true\n",
            encoding="utf-8",
        )
        with pytest.raises(PackError, match="combatants"):
            load_pack(root)
