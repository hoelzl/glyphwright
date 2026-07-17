"""Run fingerprints: what produced a piece of evidence.

Every session records engine version, pack id, and seed, so baselines invalidate
on engine or content change rather than passing against different data (design
0003 sections 14–15).
"""

from __future__ import annotations

from dataclasses import dataclass

from glyphwright import __version__

SESSION_SCHEMA = "glyphwright.session/1"


@dataclass(frozen=True, slots=True)
class RunFingerprint:
    """The identity of a run, as recorded in a transcript header."""

    engine: str
    pack: str
    seed: int
    turn: int

    @classmethod
    def create(cls, *, pack: str, seed: int, turn: int) -> RunFingerprint:
        return cls(engine=f"glyphwright {__version__}", pack=pack, seed=seed, turn=turn)

    def header(self, *, harness: bool) -> dict[str, object]:
        """The JSONL session header line."""
        return {
            "schema": SESSION_SCHEMA,
            "engine": self.engine,
            "pack": self.pack,
            "seed": self.seed,
            "harness": harness,
        }
