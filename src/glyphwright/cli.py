"""Terminal entry point: choose a frontend, then get out of the way.

Only this layer knows about terminals. Every frontend is a pure function over
frames, so the CLI's whole job is to build the run and hand over the streams.
"""

from __future__ import annotations

import argparse
import io
import sys
from collections.abc import Sequence
from typing import TextIO

from glyphwright.api import Engine, PackError, load_pack, reference_pack
from glyphwright.frontends import jsonl, plain

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
        default=DEFAULT_SEED,
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
        help="enable the introspection meta channel (:seed, :frame)",
    )
    args = parser.parse_args(argv)

    try:
        pack = reference_pack() if args.pack is None else load_pack(args.pack)
    except PackError as error:
        # The located diagnostic, as argparse reports any other bad argument.
        parser.exit(2, f"glyphwright: {error}\n")
    engine = Engine.new(pack, seed=args.seed)
    stdin = _utf8(sys.stdin, reading=True)
    stdout = _utf8(sys.stdout, reading=False)
    if args.frontend == "jsonl":
        return jsonl.run_session(engine, stdin, stdout, harness=args.harness)
    return plain.run_session(engine, stdin, stdout, harness=args.harness)


if __name__ == "__main__":
    raise SystemExit(main())
