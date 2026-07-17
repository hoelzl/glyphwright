"""The seeded stream is PCG64, and is a value rather than a generator."""

from __future__ import annotations

import pytest

from glyphwright.kernel.rng import Rng

# Cross-checked against numpy's reference PCG64 (numpy.random.PCG64.random_raw)
# by seeding it with the post-seed state of Rng.from_seed(424242). numpy is not
# a project dependency: its output is frozen here so the check is permanent and
# costs nothing. Regenerating these requires re-running that comparison.
_SEED = 424242
_REFERENCE_DRAWS = (
    15405019577986629551,
    4872354606113803457,
    12949792472829664757,
    18126797619432756875,
    11274321092223398023,
    13020727430778872767,
    9040339224474386869,
    1359271539710591923,
)


def _take(rng: Rng, count: int) -> tuple[int, ...]:
    drawn = []
    cursor = rng
    for _ in range(count):
        value, cursor = cursor.next_u64()
        drawn.append(value)
    return tuple(drawn)


def test_stream_matches_reference_pcg64() -> None:
    assert _take(Rng.from_seed(_SEED), len(_REFERENCE_DRAWS)) == _REFERENCE_DRAWS


def test_a_seed_fully_determines_the_stream() -> None:
    assert _take(Rng.from_seed(7), 16) == _take(Rng.from_seed(7), 16)


def test_different_seeds_diverge() -> None:
    assert _take(Rng.from_seed(7), 8) != _take(Rng.from_seed(8), 8)


def test_a_cursor_is_a_value_not_a_generator() -> None:
    rng = Rng.from_seed(_SEED)
    first, _ = rng.next_u64()
    again, _ = rng.next_u64()
    assert first == again, "reusing a cursor must replay the same draw"


def test_advancing_returns_a_distinct_cursor() -> None:
    rng = Rng.from_seed(_SEED)
    _, nxt = rng.next_u64()
    assert nxt != rng
    assert nxt.increment == rng.increment


def test_below_stays_in_range_and_is_reproducible() -> None:
    cursor = Rng.from_seed(11)
    drawn = []
    for _ in range(500):
        value, cursor = cursor.below(6)
        assert 0 <= value < 6
        drawn.append(value)
    replay, replay_cursor = [], Rng.from_seed(11)
    for _ in range(500):
        value, replay_cursor = replay_cursor.below(6)
        replay.append(value)
    assert drawn == replay


def test_below_covers_its_whole_range() -> None:
    cursor = Rng.from_seed(3)
    seen = set()
    for _ in range(2000):
        value, cursor = cursor.below(6)
        seen.add(value)
    assert seen == {0, 1, 2, 3, 4, 5}


def test_between_is_inclusive() -> None:
    cursor = Rng.from_seed(5)
    seen = set()
    for _ in range(2000):
        value, cursor = cursor.between(3, 5)
        assert 3 <= value <= 5
        seen.add(value)
    assert seen == {3, 4, 5}


@pytest.mark.parametrize("bound", [0, -1])
def test_below_rejects_a_non_positive_bound(bound: int) -> None:
    with pytest.raises(ValueError):
        Rng.from_seed(1).below(bound)


def test_between_rejects_an_inverted_range() -> None:
    with pytest.raises(ValueError):
        Rng.from_seed(1).between(5, 3)
