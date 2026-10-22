"""The first-pack guide's transcripts are what the engine prints.

The workshop dry run changed a message's wording, and the guide's example
went stale with every gate green. Each transcript here is an excerpt: its
output lines must appear, in order, in what the commands really print.
"""

from __future__ import annotations

import io
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from glyphwright.api import Engine, reference_pack
from glyphwright.frontends import plain
from glyphwright.kernel.commands import Move

GUIDE = Path(__file__).resolve().parents[1] / "docs" / "authoring" / "first-pack.md"
REFERENCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "glyphwright"
    / "content"
    / "packs"
    / "reference-vale"
)


def _transcript(section: str) -> list[str]:
    """The lines of the first ``text`` block under the heading ``section``."""
    text = GUIDE.read_text(encoding="utf-8")
    start = text.index(f"\n## {section}\n")
    block = re.search(r"```text\n(.*?)```", text[start:], re.DOTALL)
    assert block is not None, f"no transcript under {section!r}"
    return block.group(1).splitlines()


def _played(engine: Engine, commands: list[str], *, harness: bool) -> list[str]:
    output = io.StringIO()
    stdin = io.StringIO("".join(f"{command}\n" for command in commands))
    plain.run_session(engine, stdin, output, harness=harness)
    # The prompt shares a line with whatever follows it.
    return [re.sub(r"^(> )+", "", line) for line in output.getvalue().splitlines()]


def _assert_excerpt(transcript: list[str], engine: Engine, *, harness: bool) -> None:
    commands = [line[2:] for line in transcript if line.startswith("> ")]
    expected = [line for line in transcript if not line.startswith("> ")]
    actual = iter(_played(engine, commands, harness=harness))
    for line in expected:
        assert any(line == seen for seen in actual), (
            f"docs/authoring/first-pack.md shows {line!r}, which the engine "
            "does not print there; update the guide's transcript"
        )


def test_the_hostile_transcript_is_what_the_engine_prints() -> None:
    _assert_excerpt(
        _transcript("5. Add a hostile"),
        Engine.new(reference_pack(), seed=424242),
        harness=False,
    )


def test_the_item_transcript_is_what_the_engine_prints() -> None:
    # The excerpt starts where the sword lies.
    engine = Engine.new(reference_pack(), seed=424242)
    for token in ("east",) * 5 + ("south",) * 2:
        assert engine.step(Move(token)).accepted
    _assert_excerpt(_transcript("4. Add an item"), engine, harness=True)


@pytest.mark.e2e
def test_the_load_error_is_what_the_cli_prints(tmp_path: Path) -> None:
    (expected,) = _transcript("6. Read a load error")
    pack = tmp_path / "my-pack"
    shutil.copytree(REFERENCE, pack)
    entities = pack / "entities.toml"
    text = entities.read_text(encoding="utf-8")
    entities.write_text(text.replace("hp = 17", "hp = 30", 1), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "glyphwright.cli", "--pack", str(pack)],
        input=b"",
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 2
    assert result.stderr.decode("utf-8").strip() == expected
