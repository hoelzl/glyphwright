#!/usr/bin/env python3
"""Run every repository gate — run this script, do not copy its list.

Usage:
    uv run python scripts/check.py           # run all gates
    uv run python scripts/check.py --list    # print the gates, run nothing

The gates run in order, cheapest first, and all of them run even when one
fails, so a single run shows every problem. The command list lives here, in
code that runs, so other files name this script instead of repeating it.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable, Sequence

Gate = tuple[str, tuple[str, ...]]
Runner = Callable[[Sequence[str]], int]

GATES: tuple[Gate, ...] = (
    ("lint", (sys.executable, "-m", "ruff", "check", ".")),
    ("format", (sys.executable, "-m", "ruff", "format", "--check", ".")),
    ("documentation", (sys.executable, "scripts/docs_tool.py", "check")),
    ("types", (sys.executable, "-m", "mypy")),
    ("tests", (sys.executable, "-m", "pytest", "-q")),
)


def _subprocess_runner(command: Sequence[str]) -> int:
    return subprocess.call(list(command))


def run_gates(gates: Sequence[Gate], runner: Runner) -> list[str]:
    """Run every gate and return the names of those that failed."""
    failed: list[str] = []
    for name, command in gates:
        print(f"== {name}", flush=True)
        if runner(command) != 0:
            failed.append(name)
    return failed


def main(argv: Sequence[str] | None = None, runner: Runner | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run every repository gate.")
    parser.add_argument("--list", action="store_true", help="print, don't run")
    args = parser.parse_args(argv)
    if args.list:
        for name, command in GATES:
            print(f"{name}: {' '.join(command[1:])}")
        return 0
    failed = run_gates(GATES, runner or _subprocess_runner)
    if failed:
        print(f"check failed: {', '.join(failed)}", flush=True)
        return 1
    print("check passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
