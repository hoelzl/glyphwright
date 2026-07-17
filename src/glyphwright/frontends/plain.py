"""The plain line-oriented frontend.

Renders each frame as an IF-style transcript block with an unambiguous
delimiter. ASCII by default, because locale is part of the determinism contract
and ASCII transcripts diff cleanly (design 0003 section 12, ADR-007).

This frontend doubles as the human review format for baselines, so it renders
the reviewable subset of a frame rather than all of it: the command grammar is
machine detail and belongs in the JSONL frontend. :func:`parse` recovers exactly
what :func:`render` emits, which is what the round-trip test asserts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TextIO

from glyphwright.api import Engine
from glyphwright.frames.frame import SemanticFrame
from glyphwright.frontends.wire import decode_command
from glyphwright.harness import meta

_DELIMITER = "=="


@dataclass(frozen=True, slots=True)
class PlainProjection:
    """The part of a frame the plain frontend commits to paper.

    The round-trip test asserts ``parse(render(frame)) == project(frame)``, so
    this type names precisely what the transcript is evidence of.
    """

    turn: int
    mode: str
    area: str
    tiles: tuple[str, ...]
    messages: tuple[str, ...]
    hp: tuple[int, int] | None


def project(frame: SemanticFrame) -> PlainProjection:
    """The projection the plain transcript is expected to preserve."""
    player = next((actor for actor in frame.actors if actor.id == "player"), None)
    return PlainProjection(
        turn=frame.turn,
        mode=frame.mode,
        area=frame.viewport.area,
        tiles=frame.viewport.tiles,
        messages=frame.messages,
        hp=None if player is None else (player.hp, player.max_hp),
    )


def render(frame: SemanticFrame) -> str:
    """Render one frame as a transcript block."""
    view = project(frame)
    lines = [f"{_DELIMITER} turn {view.turn} · {view.mode} · {view.area} {_DELIMITER}"]
    lines.extend(view.tiles)
    lines.extend(view.messages)
    if view.hp is not None:
        lines.append(f"[hp {view.hp[0]}/{view.hp[1]}]")
    return "\n".join(lines)


def parse(text: str) -> PlainProjection:
    """Recover the projection from a rendered block.

    The ``== turn N · mode · area ==`` delimiter is the stable parse anchor for
    transcript tooling (0003 appendix B).
    """
    lines = text.split("\n")
    if not lines or not lines[0].startswith(_DELIMITER):
        raise ValueError("transcript block must open with a turn delimiter")

    header = lines[0].strip(f"{_DELIMITER} ").split(" · ")
    if len(header) != 3 or not header[0].startswith("turn "):
        raise ValueError(f"malformed delimiter: {lines[0]!r}")
    turn = int(header[0].removeprefix("turn "))

    body = lines[1:]
    hp: tuple[int, int] | None = None
    if body and body[-1].startswith("[hp "):
        current, _, maximum = (
            body[-1].removeprefix("[hp ").removesuffix("]").partition("/")
        )
        hp = (int(current), int(maximum))
        body = body[:-1]

    tiles = tuple(line for line in body if line and set(line) <= set("#.@~!/"))
    messages = tuple(body[len(tiles) :])
    return PlainProjection(
        turn=turn,
        mode=header[1],
        area=header[2],
        tiles=tiles,
        messages=messages,
        hp=hp,
    )


_PROMPT = "> "
_HELP = (
    "commands: move <north|east|south|west> | look | wait"
    " | take <item> | use <item> | equip <item> | quit\n"
)


def run_session(
    engine: Engine, input_stream: TextIO, output: TextIO, *, harness: bool = False
) -> int:
    """Drive a run as a human-readable transcript."""
    output.write(_HELP)
    output.write(render(engine.frame()) + "\n")

    while True:
        output.write(_PROMPT)
        output.flush()
        line = input_stream.readline()
        if not line or line.strip() == "quit":
            output.write("session ended\n")
            return 0
        if line.strip() == "help":
            output.write(_HELP)
            continue
        if line.strip().startswith(":"):
            if not harness:
                output.write("? the meta-channel needs --harness\n")
                continue
            if line.strip() == ":frame":
                # The plain reading of the current frame; --json for the wire form.
                output.write(render(engine.frame()) + "\n")
                continue
            output.write(meta.render_text(meta.handle(engine, line.strip())) + "\n")
            continue

        command = decode_command(line)
        if command is None:
            output.write(f"? {line.strip()!r} — {_HELP}")
            continue

        result = engine.step(command)
        if result.rejection is not None:
            output.write(f"? {result.rejection.reason}: {result.rejection.hint}\n")
            continue
        output.write(render(result.frame) + "\n")
