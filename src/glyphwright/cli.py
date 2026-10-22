"""Terminal entry point: choose a frontend, then get out of the way.

Only this layer knows about terminals. Every frontend is a pure function over
frames, so the CLI's whole job is to build the run and hand over the streams.
"""

from __future__ import annotations

import argparse
import io
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from glyphwright.api import Engine, PackError, load_pack, reference_pack
from glyphwright.frontends import jsonl, plain
from glyphwright.harness.recording import RecordingEngine, replay

DEFAULT_SEED = 424242


def _utf8(stream: TextIO, *, reading: bool) -> TextIO:
    """The stream as UTF-8 with ``\\n`` newlines on every platform.

    Without this, Windows pipes default to a legacy code page, and the same
    session would produce different bytes on the three CI systems. Input keeps
    undecodable bytes as surrogates so the frontends can echo them safely.
    """
    if isinstance(stream, io.TextIOWrapper):
        stream.reconfigure(
            encoding="utf-8",
            errors="surrogateescape" if reading else "strict",
            newline=None if reading else "\n",
        )
    return stream


def main(argv: Sequence[str] | None = None) -> int:
    """Run a deterministic session over stdio."""
    parser = argparse.ArgumentParser(
        prog="glyphwright",
        description="Play a deterministic RPG session over stdin and stdout.",
    )
    parser.add_argument(
        "--frontend",
        choices=("plain", "jsonl"),
        default="plain",
        help="presentation to drive the session with (default: plain)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help=f"run seed, recorded in the fingerprint (default: {DEFAULT_SEED})",
    )
    parser.add_argument(
        "--pack",
        default=None,
        help="directory of a TOML content pack (default: the built-in reference pack)",
    )
    parser.add_argument(
        "--harness",
        action="store_true",
        help="enable the introspection meta channel (:query, :seed, :frame)",
    )
    parser.add_argument(
        "--record",
        type=Path,
        default=None,
        help="write the session's recording to this new file",
    )
    parser.add_argument(
        "--replay",
        type=Path,
        default=None,
        help="verify a recording against the pack instead of playing",
    )
    args = parser.parse_args(argv)
    # v0 finding F7: replay must not depend on frontend checks it never uses.
    if args.replay is not None and args.record is not None:
        parser.error("--replay verifies an existing recording; it cannot --record")
    if args.replay is not None and args.seed is not None:
        parser.error("--replay takes its seed from the recording's header")
    seed = DEFAULT_SEED if args.seed is None else args.seed

    try:
        pack = reference_pack() if args.pack is None else load_pack(args.pack)
    except PackError as error:
        # The located diagnostic, as argparse reports any other bad argument.
        parser.exit(2, f"glyphwright: {error}\n")
    stdout = _utf8(sys.stdout, reading=False)
    if args.replay is not None:
        try:
            with args.replay.open(encoding="utf-8") as source:
                outcome = replay(pack, source)
        except OSError as error:
            parser.exit(2, f"glyphwright: cannot read recording: {error}\n")
        if outcome.ok:
            assert outcome.engine is not None
            turn = outcome.engine.fingerprint().turn
            stdout.write(f"recording verified: {_steps(outcome.steps)}, turn {turn}\n")
            return 0
        stdout.write(
            f"recording diverged after {_steps(outcome.steps)}: {outcome.problem}\n"
        )
        return 1

    stdin = _utf8(sys.stdin, reading=True)
    if args.record is None:
        return _play(Engine.new(pack, seed=seed), args, stdin, stdout)
    try:
        # A recording is a run from turn 0: never append to or replace one.
        sink = args.record.open("x", encoding="utf-8", newline="\n")
    except FileExistsError:
        parser.exit(2, f"glyphwright: refusing to overwrite {args.record}\n")
    except OSError as error:
        parser.exit(2, f"glyphwright: cannot write recording: {error}\n")
    with sink:
        engine = RecordingEngine.recording(
            pack, seed=seed, sink=sink, harness=args.harness
        )
        status = _play(engine, args, stdin, stdout)
    # On stderr, so a JSONL stream stays clean. Rejected commands are not
    # recorded, and an agent piping output away would not see them.
    sys.stderr.write(f"recorded {_steps(engine.steps)} to {args.record}\n")
    return status


def _steps(count: int) -> str:
    return f"{count} step" if count == 1 else f"{count} steps"


def _play(
    engine: Engine, args: argparse.Namespace, stdin: TextIO, stdout: TextIO
) -> int:
    if args.frontend == "jsonl":
        return jsonl.run_session(engine, stdin, stdout, harness=args.harness)
    return plain.run_session(engine, stdin, stdout, harness=args.harness)


if __name__ == "__main__":
    raise SystemExit(main())
