#!/usr/bin/env python3
"""Ask the installed Claude Code whether generated skill stubs still work.

Usage:
    uv run python scripts/probe_claude_stubs.py                 # current mode
    uv run python scripts/probe_claude_stubs.py --mode inline   # the fallback

Run it after each Claude Code update; it is not a gate, because it tests
Claude Code rather than a change to this repository, and it makes two small
model calls. It builds a throwaway repository with one probe skill, generates
that skill's stub with ``scripts/docs_tool.py``, and runs ``claude -p``
twice, with your own settings and MCP servers left out:

1. **Expansion** (decides the exit status): ``/stub-probe`` with every tool
   disabled. Claude can answer with the skill's secret token only if the stub
   delivered the skill body. With tools off it cannot read the file itself
   and hide a broken import.
2. **Automatic use** (reported only): a plain question, with only the Skill
   tool available. It shows whether Claude picks the stub on its own; a
   model's choice can vary between runs.

If the expansion probe fails in ``import`` mode and passes with
``--mode inline``, set ``STUB_MODE = "inline"`` in ``scripts/docs_tool.py``,
rebuild, and record the change as a decision.
"""

from __future__ import annotations

import argparse
import secrets
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

import docs_tool

SKILL_NAME = "stub-probe"
ISOLATION = (
    "--setting-sources",
    "project",
    "--strict-mcp-config",
    "--no-session-persistence",
    "--output-format",
    "text",
)

Runner = Callable[[Sequence[str], Path], str]


def probe_skill(token: str) -> str:
    """Return a SKILL.md whose body holds a token nothing else can know."""
    return (
        "---\n"
        f"name: {SKILL_NAME}\n"
        "description: Reports the stub probe token. Use when asked for the stub "
        "probe token.\n"
        "---\n"
        "# Stub probe\n\n"
        f"Reply with exactly this token and nothing else: {token}\n"
    )


def make_repo(root: Path, token: str, mode: str) -> None:
    """Write the probe skill and its generated stub under *root*."""
    skill = root / docs_tool.SKILLS_DIR / SKILL_NAME / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(probe_skill(token), encoding="utf-8", newline="\n")
    (root / "AGENTS.md").write_text("# Probe\n\nA throwaway repository.\n")
    for path, content in docs_tool.expected_stubs(root, mode).items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")


def probes(claude: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return ``(name, command)`` for the expansion and automatic-use probes."""
    return (
        ("expansion", (claude, "-p", f"/{SKILL_NAME}", "--tools", "", *ISOLATION)),
        (
            "automatic use",
            (
                claude,
                "-p",
                "What is the stub probe token?",
                "--tools",
                "Skill",
                *ISOLATION,
            ),
        ),
    )


def _subprocess_runner(command: Sequence[str], cwd: Path) -> str:
    result = subprocess.run(
        list(command), cwd=cwd, capture_output=True, text=True, timeout=300
    )
    return result.stdout + result.stderr


def run(mode: str, claude: str, runner: Runner) -> dict[str, bool]:
    """Run both probes in a throwaway repository; return pass/fail by name."""
    token = f"probe-{secrets.token_hex(6)}"
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        make_repo(root, token, mode)
        return {
            name: token in runner(command, root) for name, command in probes(claude)
        }


def main(argv: Sequence[str] | None = None, runner: Runner | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe Claude Code skill stubs.")
    parser.add_argument(
        "--mode", choices=["import", "inline"], default=docs_tool.STUB_MODE
    )
    args = parser.parse_args(argv)
    claude = shutil.which("claude")
    if claude is None and runner is None:
        print("claude is not on PATH; install Claude Code to run the probe")
        return 2
    results = run(args.mode, claude or "claude", runner or _subprocess_runner)
    for name, passed in results.items():
        verdict = "pass" if passed else "FAIL"
        note = "" if name == "expansion" else " (reported only)"
        print(f"{name}: {verdict}{note}  [mode: {args.mode}]")
    if not results["expansion"]:
        print(
            "The stub did not deliver the skill. Rerun with --mode inline; if"
            " that passes, switch STUB_MODE in scripts/docs_tool.py.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
