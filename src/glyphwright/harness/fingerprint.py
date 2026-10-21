"""Run fingerprints: what produced a piece of evidence.

Every session records the engine version, the rules revision, the pack id,
and the seed, so a recording refuses to replay against different rules or
data instead of passing or failing for the wrong reason.
"""

from __future__ import annotations

from dataclasses import dataclass

from glyphwright import __version__

SESSION_SCHEMA = "glyphwright.session/2"

#: Which behaviour produced a run. Bump it in any change that makes the same
#: commands produce different events, frames, or state; the pinned recording
#: under ``tests/recordings/`` fails until you do (decision 0003). It is not
#: the release version: releases and behaviour change at different times.
RULES = 1

# The header's keys and their types, checked exactly (v0 finding H4).
_HEADER_TYPES: dict[str, type] = {
    "schema": str,
    "engine": str,
    "rules": int,
    "pack": str,
    "seed": int,
    "harness": bool,
}


@dataclass(frozen=True, slots=True)
class RunFingerprint:
    """The identity of a run, as recorded in a session header."""

    engine: str
    rules: int
    pack: str
    seed: int
    turn: int

    @classmethod
    def create(cls, *, pack: str, seed: int, turn: int) -> RunFingerprint:
        return cls(
            engine=f"glyphwright {__version__}",
            rules=RULES,
            pack=pack,
            seed=seed,
            turn=turn,
        )

    def header(self, *, harness: bool) -> dict[str, object]:
        """The session header line of a JSONL stream or a recording."""
        return {
            "schema": SESSION_SCHEMA,
            "engine": self.engine,
            "rules": self.rules,
            "pack": self.pack,
            "seed": self.seed,
            "harness": harness,
        }


def header_problem(header: object) -> str | None:
    """Why ``header`` is not a valid session header, or ``None`` if it is.

    The check mirrors the committed ``session/2`` schema key by key, because
    the schema validator is a development dependency and the engine is not.
    A test keeps the two in agreement.
    """
    if not isinstance(header, dict):
        return "the session header is not a JSON object"
    if header.get("schema") != SESSION_SCHEMA:
        return f"the first line is not a {SESSION_SCHEMA} header"
    missing = sorted(_HEADER_TYPES.keys() - header.keys())
    if missing:
        return f"the session header lacks {', '.join(missing)}"
    extra = sorted(header.keys() - _HEADER_TYPES.keys())
    if extra:
        return f"the session header has unknown keys: {', '.join(extra)}"
    for key, expected in _HEADER_TYPES.items():
        value = header[key]
        # True == 1, so a boolean must not pass for an integer.
        if not isinstance(value, expected) or (
            expected is int and isinstance(value, bool)
        ):
            return f"the session header's {key} is not a {expected.__name__}: {value!r}"
    return None
