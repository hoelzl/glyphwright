"""The plain line-oriented frontend.

Renders each frame as a transcript block opened by an unambiguous delimiter.
The engine's own text is ASCII, because the transcript doubles as a reviewed
baseline and must read the same on every platform; content glyphs come from
the pack.

The plain view renders the reviewable subset of a frame rather than all of it:
the command grammar is machine detail and belongs in the JSONL frontend.
:func:`parse` recovers exactly what :func:`render` emits, which is what the
round-trip test asserts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TextIO

from glyphwright.api import Engine
from glyphwright.frames.frame import GridView, SemanticFrame, flatten
from glyphwright.frontends.jsonl import safe_echo
from glyphwright.frontends.wire import (
    VERB_SPECS,
    decode_command,
    missing_argument_hint,
)
from glyphwright.harness import meta
from glyphwright.kernel.state import PLAYER

_DELIMITER = "=="
_SEPARATOR = " | "
_HERE = "[here "
_EXITS = "[exits "
_CARRYING = "[carrying "
_INITIATIVE = "[initiative "


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
    here: tuple[str, ...] = ()
    exits: tuple[str, ...] = ()
    carrying: tuple[str, ...] = ()
    # A battle's combatants as "id hp/max", in initiative order.
    combatants: tuple[str, ...] = ()


def project(frame: SemanticFrame) -> PlainProjection:
    """The projection the plain transcript is expected to preserve."""
    player = next((actor for actor in frame.actors if actor.id == PLAYER), None)
    hp = {actor.id: f"{actor.hp}/{actor.max_hp}" for actor in frame.actors}
    viewport = frame.viewport
    return PlainProjection(
        turn=frame.turn,
        mode=frame.mode,
        area=viewport.area,
        tiles=flatten(viewport) if isinstance(viewport, GridView) else (),
        combatants=()
        if isinstance(viewport, GridView)
        else tuple(f"{c} {hp[c]}" for c in viewport.combatants if c in hp),
        messages=frame.messages,
        hp=None if player is None else (player.hp, player.max_hp),
        here=tuple(item.id for item in frame.here),
        exits=frame.exits,
        carrying=tuple(
            item.id if item.slot is None else f"{item.id} (equipped: {item.slot})"
            for item in frame.inventory
        ),
    )


def render(frame: SemanticFrame) -> str:
    """Render one frame as a transcript block."""
    view = project(frame)
    header = _SEPARATOR.join((f"turn {view.turn}", view.mode, view.area))
    lines = [f"{_DELIMITER} {header} {_DELIMITER}"]
    if view.combatants:
        lines.append(f"{_INITIATIVE}{', '.join(view.combatants)}]")
    lines.extend(view.tiles)
    lines.extend(view.messages)
    if view.here:
        lines.append(f"{_HERE}{', '.join(view.here)}]")
    if view.exits:
        lines.append(f"{_EXITS}{', '.join(view.exits)}]")
    if view.carrying:
        # Ids hold no whitespace, so ", " and " (" cannot occur inside one.
        lines.append(f"{_CARRYING}{', '.join(view.carrying)}]")
    if view.hp is not None:
        lines.append(f"[hp {view.hp[0]}/{view.hp[1]}]")
    return "\n".join(lines)


def parse(text: str) -> PlainProjection:
    """Recover the projection from a rendered block.

    The ``== turn N | mode | area ==`` delimiter is the stable parse anchor for
    transcript tooling.
    """
    lines = text.split("\n")
    if not lines or not lines[0].startswith(_DELIMITER):
        raise ValueError("transcript block must open with a turn delimiter")

    header = lines[0].strip(f"{_DELIMITER} ").split(_SEPARATOR)
    if len(header) != 3 or not header[0].startswith("turn "):
        raise ValueError(f"malformed delimiter: {lines[0]!r}")
    turn = int(header[0].removeprefix("turn "))

    body = lines[1:]
    combatants: tuple[str, ...] = ()
    if body and body[0].startswith(_INITIATIVE):
        listed = body[0].removeprefix(_INITIATIVE).removesuffix("]")
        combatants = tuple(listed.split(", "))
        body = body[1:]
    hp: tuple[int, int] | None = None
    if body and body[-1].startswith("[hp "):
        current, _, maximum = (
            body[-1].removeprefix("[hp ").removesuffix("]").partition("/")
        )
        hp = (int(current), int(maximum))
        body = body[:-1]
    carrying: tuple[str, ...] = ()
    if body and body[-1].startswith(_CARRYING):
        carrying = _listed(body[-1], _CARRYING)
        body = body[:-1]
    exits: tuple[str, ...] = ()
    if body and body[-1].startswith(_EXITS):
        exits = _listed(body[-1], _EXITS)
        body = body[:-1]
    here: tuple[str, ...] = ()
    if body and body[-1].startswith(_HERE):
        here = _listed(body[-1], _HERE)
        body = body[:-1]

    # Tiles are the leading run of space-free lines: content-independent, so
    # a pack may use any glyph. Message templates always contain spaces.
    tiles: tuple[str, ...] = ()
    for line in body:
        if not line or " " in line:
            break
        tiles = (*tiles, line)
    return PlainProjection(
        turn=turn,
        mode=header[1],
        area=header[2],
        tiles=tiles,
        messages=tuple(body[len(tiles) :]),
        hp=hp,
        here=here,
        exits=exits,
        carrying=carrying,
        combatants=combatants,
    )


def _listed(line: str, prefix: str) -> tuple[str, ...]:
    return tuple(line.removeprefix(prefix).removesuffix("]").split(", "))


_PROMPT = "> "


def help_line(frame: SemanticFrame) -> str:
    """Commands the frame's grammar advertises right now.

    Derived from the grammar rather than hand-written, so the help can never
    drift from what the engine actually accepts.
    """
    verbs = [VERB_SPECS[verb].usage() for verb in frame.commands.verb_names()]
    return "commands: " + " | ".join((*verbs, "quit")) + "\n"


def legend_line(frame: SemanticFrame) -> str:
    """What each glyph on the map stands for; empty when there is no map.

    The workshop dry run had to guess that ``/`` is the sword: the legend was
    in every JSONL frame and nowhere in the transcript.
    """
    viewport = frame.viewport
    if not isinstance(viewport, GridView):
        return ""
    entries = ", ".join(f"{glyph} {label}" for glyph, label in viewport.legend)
    return f"map: {entries}\n"


def run_session(
    engine: Engine, input_stream: TextIO, output: TextIO, *, harness: bool = False
) -> int:
    """Drive a run as a human-readable transcript.

    The command list is printed again whenever the verbs on offer change, so
    a new possibility, such as ``equip`` after taking a sword, is announced
    rather than left for ``help`` to reveal. The map legend is printed at the
    start, with ``help``, and whenever the player enters another area.
    """
    offered = engine.frame().commands.verb_names()
    area = engine.frame().viewport.area
    output.write(help_line(engine.frame()))
    output.write(legend_line(engine.frame()))
    output.write(render(engine.frame()) + "\n")

    while True:
        output.write(_PROMPT)
        output.flush()
        raw = input_stream.readline()
        line = safe_echo(raw)
        if not raw or line == "quit":
            output.write("session ended\n")
            return 0
        if line == "help":
            output.write(help_line(engine.frame()))
            output.write(legend_line(engine.frame()))
            continue
        if line.startswith(":"):
            if not harness:
                output.write("? the meta channel needs --harness\n")
                continue
            if line == ":frame":
                # The plain reading of the current frame; --json for the wire form.
                output.write(render(engine.frame()) + "\n")
                continue
            output.write(meta.render_text(meta.handle(engine, line)) + "\n")
            continue

        command = decode_command(line)
        if command is None:
            asked = missing_argument_hint(engine.frame(), line)
            if asked is not None:
                output.write(f"? {asked}\n")
            else:
                output.write(f"? {line!r}: {help_line(engine.frame())}")
            continue

        result = engine.step(command)
        if result.rejection is not None:
            output.write(f"? {result.rejection.reason}: {result.rejection.hint}\n")
            continue
        output.write(render(result.frame) + "\n")
        if result.frame.commands.verb_names() != offered:
            offered = result.frame.commands.verb_names()
            output.write(help_line(result.frame))
        if result.frame.viewport.area != area:
            area = result.frame.viewport.area
            output.write(legend_line(result.frame))
