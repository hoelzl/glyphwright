"""Terminal entry point: choose a frontend, then get out of the way.

Only this layer knows about terminals. Both frontends are pure functions over
frames, so the CLI's whole job is to build the run and hand over the streams
(design 0003 section 4).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

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
    args = parser.parse_args(argv)

    engine = Engine.new(reference_pack(), seed=args.seed)
    if args.frontend == "jsonl":
        return jsonl.run_session(engine, sys.stdin, sys.stdout, harness=args.harness)
    if args.frontend == "tui":
        if not sys.stdin.isatty():
            # Fail before touching the terminal: piped input belongs to the
            # plain and JSONL frontends.
            parser.error("--frontend tui needs an interactive terminal")
        from glyphwright.frontends.tui import session as tui_session

        return tui_session.run_session(engine, None, sys.stdout, harness=args.harness)
    return plain.run_session(engine, sys.stdin, sys.stdout, harness=args.harness)


if __name__ == "__main__":
    raise SystemExit(main())
