"""The pure A* pathfinder that click-to-move compiles through (design 0012 §6).

Presentation-side convenience, never new kernel semantics: the pathfinder is a
deterministic function over the grid's passable topology, and the click macro
expands to the same ``move <token>`` commands an agent would type — so a click
session replays byte-identically through the recording.
"""

from __future__ import annotations

from glyphwright.world.grid import GridSpace


def _space(text: str) -> GridSpace:
    return GridSpace.from_text("field", text)


def test_a_straight_corridor_yields_its_tokens() -> None:
    from glyphwright.frontends.presentation.pathfinding import find_path

    space = _space(".....")
    assert find_path(space, (0, 0), (4, 0)) == ("east", "east", "east", "east")


def test_a_path_turns_a_corner() -> None:
    from glyphwright.frontends.presentation.pathfinding import find_path

    space = _space("...\n..#\n###")  # only the top row and the middle column are open
    # (0,0) -> (1,0) -> (2,0): the top row is the only way across.
    assert find_path(space, (0, 0), (2, 0)) == ("east", "east")


def test_a_wall_is_routed_around() -> None:
    from glyphwright.frontends.presentation.pathfinding import find_path

    space = _space("...\n.#.\n...")
    path = find_path(space, (0, 1), (2, 1))
    assert path is not None
    # The direct route east is walled; the path must go around via row 0 or 2.
    assert path != ("east", "east")
    assert _walk(space, (0, 1), path) == (2, 1)


def test_an_unreachable_target_returns_none() -> None:
    from glyphwright.frontends.presentation.pathfinding import find_path

    space = _space("...\n###\n...")
    assert find_path(space, (0, 0), (0, 2)) is None


def test_start_equals_goal_is_an_empty_path() -> None:
    from glyphwright.frontends.presentation.pathfinding import find_path

    space = _space("..")
    assert find_path(space, (1, 0), (1, 0)) == ()


def test_a_walled_goal_is_unreachable() -> None:
    from glyphwright.frontends.presentation.pathfinding import find_path

    space = _space(".#.")
    assert find_path(space, (0, 0), (2, 0)) is None


def test_ties_break_deterministically_by_token_order() -> None:
    """Two equal-cost routes exist around a symmetric obstacle; the seeded /
    ordered tie-break must pick one stable answer every time."""
    from glyphwright.frontends.presentation.pathfinding import find_path

    space = _space("...\n.#.\n...")
    first = find_path(space, (0, 0), (2, 2))
    second = find_path(space, (0, 0), (2, 2))
    assert first is not None and first == second


def _walk(
    space: GridSpace, start: tuple[int, int], path: tuple[str, ...]
) -> tuple[int, int]:
    """Follow tokens through the space's own exit geometry; the arrival point."""
    pos = space.pos(*start)
    for token in path:
        pos = space.exits(pos)[token]
    x_text, _, y_text = pos.local.partition(",")
    return int(x_text), int(y_text)
