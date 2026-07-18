"""Terminal entry point: choose a frontend, then get out of the way.

Only this layer knows about terminals. Both frontends are pure functions over
frames, so the CLI's whole job is to build the run and hand over the streams
(design 0003 section 4).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from glyphwright.api import Engine
from glyphwright.content.pack import reference_pack
from glyphwright.frontends import jsonl, plain

DEFAULT_SEED = 424242


def main(argv: Sequence[str] | None = None) -> int:
    """Run a deterministic session over stdio."""
    parser = argparse.ArgumentParser(
        prog="glyphwright",
        description="Play a deterministic terminal RPG session.",
    )
    parser.add_argument(
        "--frontend",
        choices=("plain", "jsonl", "tui"),
        default="plain",
        help="presentation to drive the session with (default: plain)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="explicit run seed, recorded in the fingerprint "
        f"(default: {DEFAULT_SEED})",
    )
    parser.add_argument(
        "--harness",
        action="store_true",
        help="enable the introspection meta-channel (capability gate)",
    )
    parser.add_argument(
        "--pack",
        type=Path,
        default=None,
        help="directory of a TOML content pack (default: the built-in reference pack)",
    )
    parser.add_argument(
        "--record",
        type=Path,
        default=None,
        help="append the session's accepted commands to this recording file",
    )
    parser.add_argument(
        "--replay",
        type=Path,
        default=None,
        help="verify a recording against the chosen pack instead of playing",
    )
    args = parser.parse_args(argv)

    if args.pack is not None:
        from glyphwright.content.loader import PackError, load_pack

        try:
            pack = load_pack(args.pack)
        except PackError as error:
            parser.error(str(error))
    else:
        pack = reference_pack()

    if args.replay is not None:
        from glyphwright.harness.recording import replay

        outcome = replay(pack, args.replay.read_text(encoding="utf-8").splitlines())
        if outcome.ok:
            assert outcome.engine is not None
            print(
                f"recording verified: {outcome.steps} steps, "
                f"turn {outcome.engine.fingerprint().turn}"
            )
            return 0
        print(f"recording diverged after {outcome.steps} steps: {outcome.problem}")
        return 1

    if args.record is not None:
        from glyphwright.harness.recording import RecordingEngine

        with args.record.open("w", encoding="utf-8", newline="\n") as sink:
            engine: Engine = RecordingEngine.recording(
                pack, seed=args.seed, sink=sink, harness=args.harness
            )
            return _play(parser, engine, args.frontend, harness=args.harness)
    return _play(
        parser, Engine.new(pack, seed=args.seed), args.frontend, harness=args.harness
    )


def _play(
    parser: argparse.ArgumentParser,
    engine: Engine,
    frontend: str,
    *,
    harness: bool,
) -> int:
    if frontend == "jsonl":
        return jsonl.run_session(engine, sys.stdin, sys.stdout, harness=harness)
    if frontend == "tui":
        if not sys.stdin.isatty():
            # Fail before touching the terminal: piped input belongs to the
            # plain and JSONL frontends.
            parser.error("--frontend tui needs an interactive terminal")
        from glyphwright.frontends.tui import session as tui_session

        return tui_session.run_session(engine, None, sys.stdout, harness=harness)
    return plain.run_session(engine, sys.stdin, sys.stdout, harness=harness)


if __name__ == "__main__":
    raise SystemExit(main())
