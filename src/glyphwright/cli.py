"""Terminal entry point: choose a frontend, then get out of the way.

Only this layer knows about terminals (and, for the gui frontend, windows).
Every frontend is a pure function over frames, so the CLI's whole job is to
build the run and hand over the streams (design 0003 section 4).
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
        choices=("plain", "jsonl", "tui", "gui"),
        default="plain",
        help="presentation to drive the session with (default: plain)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
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
        help="write the session's recording to this file (refuses to overwrite)",
    )
    parser.add_argument(
        "--replay",
        type=Path,
        default=None,
        help="verify a recording against the chosen pack instead of playing",
    )
    args = parser.parse_args(argv)

    if args.replay is not None and args.record is not None:
        parser.error("--replay verifies an existing recording; it cannot --record")
    if args.replay is not None and args.seed is not None:
        parser.error("--replay takes its seed from the recording's header")
    seed = args.seed if args.seed is not None else DEFAULT_SEED

    if args.frontend == "tui" and not sys.stdin.isatty():
        # Fail before touching the terminal — or any recording file: piped
        # input belongs to the plain and JSONL frontends.
        parser.error("--frontend tui needs an interactive terminal")

    if args.frontend == "gui":
        # Probe before building the run, so a missing extra fails with an
        # install hint instead of a traceback (0011 §6).
        import os

        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        try:
            import pygame  # noqa: F401
        except ImportError:
            parser.error(
                "the gui frontend needs the optional extra: "
                'pip install "glyphwright[gui]"'
            )

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

        try:
            with args.replay.open(encoding="utf-8") as source:
                outcome = replay(pack, source)
        except OSError as error:
            parser.error(f"cannot read recording: {error}")
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

        if args.record.exists():
            # A recording is a run from turn 0; there is nothing to append
            # to and silently destroying the old run would be data loss.
            parser.error(f"refusing to overwrite existing recording {args.record}")
        try:
            sink = args.record.open("x", encoding="utf-8", newline="\n")
        except OSError as error:
            parser.error(f"cannot write recording: {error}")
        with sink:
            engine: Engine = RecordingEngine.recording(
                pack, seed=seed, sink=sink, harness=args.harness
            )
            return _play(engine, args.frontend, harness=args.harness)
    return _play(Engine.new(pack, seed=seed), args.frontend, harness=args.harness)


def _play(engine: Engine, frontend: str, *, harness: bool) -> int:
    if frontend == "jsonl":
        return jsonl.run_session(engine, sys.stdin, sys.stdout, harness=harness)
    if frontend == "tui":
        from glyphwright.frontends.tui import session as tui_session

        return tui_session.run_session(engine, None, sys.stdout, harness=harness)
    if frontend == "gui":
        from glyphwright.frontends.gui import session as gui_session

        return gui_session.run_session(engine, harness=harness)
    return plain.run_session(engine, sys.stdin, sys.stdout, harness=harness)


if __name__ == "__main__":
    raise SystemExit(main())
