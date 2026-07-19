"""Run fingerprints: what produced a piece of evidence.

Every session records engine version, pack id, and seed, so baselines invalidate
on engine or content change rather than passing against different data (design
0003 sections 14–15). ``glyphwright.session/2`` adds two *optional* terms for
presentation runs (design 0012 §5/§6): a coarse **oracle fingerprint** (which
UE5 oracle a Tier-2 run consulted) and a **manifest fingerprint** (the
presentation manifest's hash). Both are absent for headless/Tier-1 runs, so a
``session/1`` header is semantically a ``session/2`` header with them unset —
which is why replay accepts either (0003 §14; 0012 §11.5).
"""

from __future__ import annotations

from dataclasses import dataclass

from glyphwright import __version__

SESSION_SCHEMA = "glyphwright.session/2"

# The schema versions replay accepts: ``session/1`` recordings predate the
# oracle/manifest terms, so they are read as ``session/2`` with both absent.
COMPATIBLE_SESSION_SCHEMAS = frozenset({"glyphwright.session/1", SESSION_SCHEMA})


@dataclass(frozen=True, slots=True)
class OracleFingerprint:
    """The coarse identity of the oracle a Tier-2 run consulted (0012 §6/§11.5).

    Deliberately coarse — the level path, the UE5/plugin version, and the set of
    bound semantic-position keys, hashed to one opaque string. It answers "is
    this the same map, same plugin build, same set of semantic positions?" and
    nothing more: collision-geometry drift is *not* encoded here (it is caught
    by the separate drift-detection audit, not by per-run fingerprinting).
    """

    level: str
    plugin: str
    positions: str

    def as_dict(self) -> dict[str, str]:
        return {"level": self.level, "plugin": self.plugin, "positions": self.positions}


@dataclass(frozen=True, slots=True)
class RunFingerprint:
    """The identity of a run, as recorded in a transcript header.

    ``oracle`` and ``manifest`` are ``None`` for Tier-1 runs: their absence is
    what makes a ``session/1`` header a degenerate ``session/2`` one.
    """

    engine: str
    pack: str
    seed: int
    turn: int
    oracle: OracleFingerprint | None = None
    manifest: str | None = None

    @classmethod
    def create(cls, *, pack: str, seed: int, turn: int) -> RunFingerprint:
        return cls(engine=f"glyphwright {__version__}", pack=pack, seed=seed, turn=turn)

    def header(self, *, harness: bool) -> dict[str, object]:
        """The JSONL session header line."""
        header: dict[str, object] = {
            "schema": SESSION_SCHEMA,
            "engine": self.engine,
            "pack": self.pack,
            "seed": self.seed,
            "harness": harness,
        }
        if self.oracle is not None:
            header["oracle"] = self.oracle.as_dict()
        if self.manifest is not None:
            header["manifest"] = self.manifest
        return header
