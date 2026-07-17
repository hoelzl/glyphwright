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
from glyphwright.frames.frame import GridView, MenuView, RoomView, SemanticFrame
from glyphwright.frontends.wire import decode_command
from glyphwright.harness import meta

_DELIMITER = "=="
_EXITS_ANCHOR = "Exits: "


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
    combatants: tuple[str, ...] = ()
    room: tuple[str, ...] = ()
    exits: tuple[str, ...] = ()


def _room_lines(viewport: RoomView) -> tuple[str, ...]:
    lines = [viewport.name, viewport.description]
    if viewport.contents:
        lines.append(f"You see: {', '.join(viewport.contents)}.")
    return tuple(lines)


def project(frame: SemanticFrame) -> PlainProjection:
    """The projection the plain transcript is expected to preserve."""
    player = next((actor for actor in frame.actors if actor.id == "player"), None)
    combatants: tuple[str, ...] = ()
    room: tuple[str, ...] = ()
    exits: tuple[str, ...] = ()
    if isinstance(frame.viewport, MenuView):
        combatants = tuple(
            f"{actor.id} {actor.hp}/{actor.max_hp}" for actor in frame.actors
        )
    if isinstance(frame.viewport, RoomView):
        room = _room_lines(frame.viewport)
        exits = frame.viewport.exits
    return PlainProjection(
        turn=frame.turn,
        mode=frame.mode,
        area=frame.viewport.area,
        tiles=frame.viewport.tiles if isinstance(frame.viewport, GridView) else (),
        messages=frame.messages,
        hp=None if player is None else (player.hp, player.max_hp),
        combatants=combatants,
        room=room,
        exits=exits,
    )


def render(frame: SemanticFrame) -> str:
    """Render one frame as a transcript block."""
    view = project(frame)
    lines = [f"{_DELIMITER} turn {view.turn} · {view.mode} · {view.area} {_DELIMITER}"]
    lines.extend(view.tiles)
    lines.extend(view.room)
    if view.exits:
        lines.append(f"{_EXITS_ANCHOR}{', '.join(view.exits)}.")
    lines.extend(f"* {combatant}" for combatant in view.combatants)
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

    combatants = tuple(
        line.removeprefix("* ") for line in body if line.startswith("* ")
    )
    body = [line for line in body if not line.startswith("* ")]

    # A room block runs from the header to its "Exits:" anchor line.
    room: tuple[str, ...] = ()
    exits: tuple[str, ...] = ()
    anchored = [i for i, line in enumerate(body) if line.startswith(_EXITS_ANCHOR)]
    if anchored:
        cut = anchored[0]
        room = tuple(body[:cut])
        exits = tuple(
            body[cut].removeprefix(_EXITS_ANCHOR).removesuffix(".").split(", ")
        )
        body = body[cut + 1 :]

    # Tiles are the leading run of space-free lines: content-independent, so
    # a pack may use any glyph. Message templates always contain spaces.
    tiles: tuple[str, ...] = ()
    for line in body:
        if not line or " " in line:
            break
        tiles = (*tiles, line)
    messages = tuple(body[len(tiles) :])
    return PlainProjection(
        turn=turn,
        mode=header[1],
        area=header[2],
        tiles=tiles,
        messages=messages,
        hp=hp,
        combatants=combatants,
        room=room,
        exits=exits,
    )


_PROMPT = "> "
_PLACEHOLDERS = {
    "move": "<exit>",
    "take": "<item>",
    "use": "<item>",
    "equip": "<item>",
    "attack": "<target>",
}


def help_line(frame: SemanticFrame) -> str:
    """Commands the frame's grammar advertises right now.

    Derived from the grammar rather than hand-written, so the help can never
    drift from what the engine actually accepts.
    """
    verbs = [
        f"{verb} {_PLACEHOLDERS[verb]}" if verb in _PLACEHOLDERS else verb
        for verb in frame.commands.verb_names()
    ]
    return "commands: " + " | ".join((*verbs, "quit")) + "\n"


def run_session(
    engine: Engine, input_stream: TextIO, output: TextIO, *, harness: bool = False
) -> int:
    """Drive a run as a human-readable transcript."""
    output.write(help_line(engine.frame()))
    output.write(render(engine.frame()) + "\n")

    while True:
        output.write(_PROMPT)
        output.flush()
        line = input_stream.readline()
        if not line or line.strip() == "quit":
            output.write("session ended\n")
            return 0
        if line.strip() == "help":
            output.write(help_line(engine.frame()))
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
            output.write(f"? {line.strip()!r} — {help_line(engine.frame())}")
            continue

        result = engine.step(command)
        if result.rejection is not None:
            output.write(f"? {result.rejection.reason}: {result.rejection.hint}\n")
            continue
        output.write(render(result.frame) + "\n")
