"""Deterministic randomness: an immutable cursor into a seeded PCG64 stream.

The engine never reads ambient entropy. Every random draw advances an explicit
cursor that lives in :class:`~glyphwright.kernel.state.WorldState`, so replaying
from a snapshot resumes the exact stream (design 0003 section 5.4).

The generator is PCG64 in its XSL-RR variant: a 128-bit LCG whose output stage
xor-shifts the state's high half onto its low half and then rotates by the top
six bits of state. Constants are O'Neill's reference values (pcg-random.org).
"""

from __future__ import annotations

from dataclasses import dataclass

_MASK_128 = (1 << 128) - 1
_MASK_64 = (1 << 64) - 1

_MULTIPLIER = 0x2360ED051FC65DA44385DF649FCCF645
_DEFAULT_INCREMENT = 0x5851F42D4C957F2D14057B7EF767814F


def _advance(state: int, increment: int) -> int:
    return (state * _MULTIPLIER + increment) & _MASK_128


def _output(state: int) -> int:
    rotation = state >> 122
    xor_shifted = ((state >> 64) ^ state) & _MASK_64
    return (
        (xor_shifted >> rotation) | (xor_shifted << ((64 - rotation) & 63))
    ) & _MASK_64


@dataclass(frozen=True, slots=True)
class Rng:
    """An immutable position in a PCG64 stream.

    Draw methods return the value together with the successor cursor; nothing is
    mutated, so a cursor may be reused to replay a draw.
    """

    state: int
    increment: int = _DEFAULT_INCREMENT

    @classmethod
    def from_seed(cls, seed: int) -> Rng:
        """Construct the stream a run's seed names.

        Follows the reference seeding routine: step from zero, add the seed,
        step again.
        """
        increment = _DEFAULT_INCREMENT
        state = _advance(0, increment)
        state = (state + seed) & _MASK_128
        return cls(state=_advance(state, increment), increment=increment)

    def next_u64(self) -> tuple[int, Rng]:
        """Draw one 64-bit value and return it with the successor cursor.

        The stream steps *before* it emits, matching the reference routine; the
        emitted value is a function of the new state, never the current one.
        """
        state = _advance(self.state, self.increment)
        return _output(state), Rng(state=state, increment=self.increment)

    def below(self, bound: int) -> tuple[int, Rng]:
        """Draw uniformly from ``range(bound)`` without modulo bias."""
        if bound <= 0:
            raise ValueError("bound must be positive")
        # Rejection-sample the largest multiple of ``bound`` that fits in 64 bits.
        limit = (1 << 64) - ((1 << 64) % bound)
        cursor = self
        while True:
            value, cursor = cursor.next_u64()
            if value < limit:
                return value % bound, cursor

    def between(self, low: int, high: int) -> tuple[int, Rng]:
        """Draw uniformly from the inclusive range ``[low, high]``."""
        if high < low:
            raise ValueError("high must not be below low")
        value, cursor = self.below(high - low + 1)
        return low + value, cursor
