"""The TOML content-pack loader: text in, a validated ``ContentPack`` out.

The loader maps tables one-to-one onto the constructors that already validate
content. Its own jobs are *shape* and *location*: every value is checked
against its expected TOML type before a constructor sees it, and every error
names the file and, where it can, the line. It reads no files; the caller
hands it the files' text, which keeps the core free of I/O.

``tomllib`` reports positions only for syntax errors. For everything else the
loader indexes the ``[[grid]]`` and ``[[entity]]`` headers in the source: the
k-th header defines the k-th table, so an error about an entity or an area is
reported at its header. When the index and the parsed data disagree, the line
is left out rather than guessed.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from typing import Any

from glyphwright.content.pack import ContentError, ContentPack
from glyphwright.world.entities import (
    Actor,
    Blocker,
    Consumable,
    Entity,
    Equippable,
    Item,
    Portal,
    Position,
    Renderable,
    StatModifier,
)
from glyphwright.world.grid import GridSpace
from glyphwright.world.space import PosId

PACK_FILE = "pack.toml"
AREAS_FILE = "areas.toml"
ENTITIES_FILE = "entities.toml"
REQUIRED_FILES = (PACK_FILE, AREAS_FILE, ENTITIES_FILE)

# Parts of the format that later slices support. A pack that uses them fails
# with this message instead of "unknown key", so a typo and a missing feature
# read differently. Each slice moves its entries into the specs below.
_LATER = "is not supported by this engine version"
_LATER_FILES = frozenset({"abilities.toml", "presentation.toml", "tileset.toml"})
_LATER_AREA_SECTIONS = frozenset({"rooms"})
_LATER_GRID_KEYS = frozenset({"fov"})
_LATER_COMPONENTS = frozenset({"ai", "openable", "dialogue"})
_LATER_ACTOR_KEYS = frozenset({"mp", "max_mp", "abilities", "perks"})
_LATER_CONSUMABLE_KEYS = frozenset({"mana"})

Spec = Mapping[str, tuple[bool, type | None]]

PACK_SPEC: Spec = {"name": (True, str)}
GRID_SPEC: Spec = {"area": (True, str), "rows": (True, str)}
ENTITY_SPEC: Spec = {
    "id": (True, str),
    "position": (False, str),
    "blocker": (False, bool),
    "actor": (False, dict),
    "renderable": (False, dict),
    "portal": (False, dict),
    "item": (False, dict),
    "consumable": (False, dict),
    "equippable": (False, dict),
}
ACTOR_SPEC: Spec = {
    "name": (True, str),
    "hp": (True, int),
    "max_hp": (True, int),
    "stats": (False, dict),
}
RENDERABLE_SPEC: Spec = {"glyph": (True, str), "label": (True, str)}
PORTAL_SPEC: Spec = {"token": (True, str), "to": (True, str)}
ITEM_SPEC: Spec = {"name": (True, str)}
CONSUMABLE_SPEC: Spec = {"heal": (True, int)}
EQUIPPABLE_SPEC: Spec = {"slot": (True, str), "modifiers": (False, list)}
MODIFIER_SPEC: Spec = {"stat": (True, str), "op": (True, str), "value": (True, int)}


class PackError(ValueError):
    """A content-pack problem, located as precisely as the source allows."""

    def __init__(
        self, file: str | None, line: int | None, column: int | None, message: str
    ) -> None:
        super().__init__(message)
        self.file = file
        self.line = line
        self.column = column
        self.message = message

    def __str__(self) -> str:
        place = ":".join(
            str(part)
            for part in (self.file, self.line, self.column)
            if part is not None
        )
        return f"{place}: {self.message}" if place else self.message


class _Located:
    """Raises errors located at one table: a file and its header line."""

    def __init__(self, file: str, line: int | None, where: str) -> None:
        self.file = file
        self.line = line
        self.where = where

    def fail(self, problem: str) -> PackError:
        return PackError(self.file, self.line, None, f"{self.where}: {problem}")

    def take(
        self, table: Mapping[str, Any], spec: Spec, later: frozenset[str]
    ) -> dict[str, Any]:
        """Exactly the allowed keys, type-checked; anything else is an error."""
        taken: dict[str, Any] = {}
        for key in table:
            if key in later:
                raise self.fail(f"{key!r} {_LATER}")
            if key not in spec:
                raise self.fail(f"unknown key {key!r}")
        for key, (required, expected) in spec.items():
            if key not in table:
                if required:
                    raise self.fail(f"missing required key {key!r}")
                continue
            value = table[key]
            if expected is not None and not _is(value, expected):
                raise self.fail(f"{key!r} must be {_name(expected)}, got {value!r}")
            taken[key] = value
        return taken

    def pos(self, text: str) -> PosId:
        try:
            return PosId.parse(text)
        except ValueError as error:
            raise self.fail(str(error)) from error


def _is(value: Any, expected: type) -> bool:
    if expected is int and isinstance(value, bool):
        return False  # bool is an int in Python, but not in content
    return isinstance(value, expected)


def _name(expected: type) -> str:
    return {
        str: "a string",
        int: "an integer",
        bool: "true or false",
        dict: "a table",
    }.get(expected, expected.__name__)


_TOML_POSITION = re.compile(r"\s*\(at line (\d+), column (\d+)\)$")


def _parse_toml(file: str, text: str) -> dict[str, Any]:
    try:
        # v2 finding N6: a UTF-8 byte-order mark is a syntax error to tomllib.
        return tomllib.loads(text.removeprefix("﻿"))
    except tomllib.TOMLDecodeError as error:
        message = str(error)
        line = getattr(error, "lineno", None)
        column = getattr(error, "colno", None)
        match = _TOML_POSITION.search(message)
        if match is not None:
            line = line or int(match.group(1))
            column = column or int(match.group(2))
            message = message[: match.start()]
        if hasattr(error, "msg"):
            message = str(error.msg)
        raise PackError(file, line, column, message) from error


def header_lines(text: str, name: str) -> list[int]:
    """The line of each ``[[name]]`` header, in order, outside strings.

    Grid rows live in multi-line strings, so a scanner that ignored strings
    could mistake a row for a header; this one skips strings and comments.
    """
    header = re.compile(rf"\[\[\s*{re.escape(name)}\s*\]\]\s*(#.*)?$")
    found = []
    in_string: str | None = None
    for number, line in enumerate(text.removeprefix("﻿").splitlines(), start=1):
        starts_outside = in_string is None
        index = 0
        while index < len(line):
            if in_string is not None:
                end = line.find(in_string, index)
                if end == -1:
                    break
                index = end + 3
                in_string = None
                continue
            char = line[index]
            if char == "#":
                break
            if line.startswith(('"""', "'''"), index):
                in_string = line[index : index + 3]
                index += 3
            elif char in "\"'":
                index = _skip_string(line, index)
            else:
                index += 1
        if starts_outside and header.match(line.strip()):
            found.append(number)
    return found


def _skip_string(line: str, start: int) -> int:
    """The index just past a one-line string that opens at ``start``."""
    quote = line[start]
    index = start + 1
    while index < len(line):
        if quote == '"' and line[index] == "\\":
            index += 2
            continue
        if line[index] == quote:
            return index + 1
        index += 1
    return index


def _tables(
    file: str, data: dict[str, Any], key: str, lines: list[int]
) -> list[tuple[int | None, dict[str, Any]]]:
    """An array of tables, each paired with its header line when known."""
    value = data.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise PackError(
            file, None, None, f"{key!r} must be an array of tables ([[{key}]])"
        )
    known: list[int | None] = list(lines)
    if len(known) != len(value):
        known = [None] * len(value)
    return list(zip(known, value, strict=True))


def _top_level(
    file: str, data: dict[str, Any], allowed: str, later: frozenset[str]
) -> None:
    for key in data:
        if key in later:
            raise PackError(file, None, None, f"{key!r} {_LATER}")
        if key != allowed:
            raise PackError(file, None, None, f"unknown key {key!r}")


def _areas(text: str) -> tuple[list[GridSpace], list[int | None]]:
    data = _parse_toml(AREAS_FILE, text)
    _top_level(AREAS_FILE, data, "grid", _LATER_AREA_SECTIONS)
    areas, lines = [], []
    for line, table in _tables(AREAS_FILE, data, "grid", header_lines(text, "grid")):
        located = _Located(AREAS_FILE, line, f"grid area {table.get('area', '?')!r}")
        fields = located.take(table, GRID_SPEC, _LATER_GRID_KEYS)
        try:
            areas.append(GridSpace.from_text(fields["area"], fields["rows"]))
        except ValueError as error:
            raise located.fail(str(error)) from error
        lines.append(line)
    return areas, lines


def _entities(text: str) -> tuple[list[Entity], list[int | None]]:
    data = _parse_toml(ENTITIES_FILE, text)
    _top_level(ENTITIES_FILE, data, "entity", frozenset())
    entities, lines = [], []
    for line, table in _tables(
        ENTITIES_FILE, data, "entity", header_lines(text, "entity")
    ):
        located = _Located(ENTITIES_FILE, line, f"entity {table.get('id', '?')!r}")
        entities.append(_entity(located, table))
        lines.append(line)
    return entities, lines


def _entity(located: _Located, table: Mapping[str, Any]) -> Entity:
    fields = located.take(table, ENTITY_SPEC, _LATER_COMPONENTS)
    actor = renderable = portal = item = consumable = equippable = None
    if "actor" in fields:
        actor_fields = located.take(fields["actor"], ACTOR_SPEC, _LATER_ACTOR_KEYS)
        stats = _stats(located, actor_fields.pop("stats", {}))
        actor = Actor(**actor_fields, base_stats=stats)
    if "item" in fields:
        item = Item(**located.take(fields["item"], ITEM_SPEC, frozenset()))
    if "consumable" in fields:
        consumable = Consumable(
            **located.take(
                fields["consumable"], CONSUMABLE_SPEC, _LATER_CONSUMABLE_KEYS
            )
        )
    if "equippable" in fields:
        equippable_fields = located.take(
            fields["equippable"], EQUIPPABLE_SPEC, frozenset()
        )
        modifiers = tuple(
            _modifier(located, entry)
            for entry in equippable_fields.get("modifiers", [])
        )
        equippable = Equippable(slot=equippable_fields["slot"], modifiers=modifiers)
    if "renderable" in fields:
        renderable = Renderable(
            **located.take(fields["renderable"], RENDERABLE_SPEC, frozenset())
        )
    if "portal" in fields:
        portal_fields = located.take(fields["portal"], PORTAL_SPEC, frozenset())
        portal = Portal(
            token=portal_fields["token"], to=located.pos(portal_fields["to"])
        )
    return Entity(
        id=fields["id"],
        position=Position(at=located.pos(fields["position"]))
        if "position" in fields
        else None,
        actor=actor,
        blocker=Blocker() if fields.get("blocker") else None,
        renderable=renderable,
        portal=portal,
        item=item,
        consumable=consumable,
        equippable=equippable,
    )


def _stats(located: _Located, table: Mapping[str, Any]) -> tuple[tuple[str, int], ...]:
    """An actor's stats table: stat names to integers, sorted by name."""
    for stat, value in table.items():
        if not _is(value, int):
            raise located.fail(f"stat {stat!r} must be an integer, got {value!r}")
    return tuple(sorted(table.items()))


def _modifier(located: _Located, entry: Any) -> StatModifier:
    if not isinstance(entry, dict):
        raise located.fail("each modifier must be a table: { stat, op, value }")
    fields = located.take(entry, MODIFIER_SPEC, frozenset())
    try:
        return StatModifier(**fields)
    except ValueError as error:
        raise located.fail(str(error)) from error


def parse_pack(sources: Mapping[str, str]) -> ContentPack:
    """Build a pack from its files' text, keyed by file name.

    Raises :class:`PackError` for every problem, at the first one found.
    """
    for name in sorted(sources):
        if name in _LATER_FILES:
            raise PackError(name, None, None, f"this file {_LATER}")
        if name not in REQUIRED_FILES:
            raise PackError(name, None, None, "unknown file in a content pack")
    for name in REQUIRED_FILES:
        if name not in sources:
            raise PackError(name, None, None, "file is missing")

    manifest = _Located(PACK_FILE, None, "pack").take(
        _parse_toml(PACK_FILE, sources[PACK_FILE]), PACK_SPEC, frozenset()
    )
    areas, area_lines = _areas(sources[AREAS_FILE])
    entities, entity_lines = _entities(sources[ENTITIES_FILE])
    try:
        return ContentPack(
            name=manifest["name"], areas=tuple(areas), entities=tuple(entities)
        )
    except ContentError as error:
        raise _locate(error, areas, area_lines, entities, entity_lines) from error


def _locate(
    error: ContentError,
    areas: list[GridSpace],
    area_lines: list[int | None],
    entities: list[Entity],
    entity_lines: list[int | None],
) -> PackError:
    """Point a content error at the header of the table it is about."""
    match error.subject:
        case ("area", name):
            indices = [i for i, space in enumerate(areas) if space.area == name]
            file, lines = AREAS_FILE, area_lines
        case ("entity", entity_id):
            indices = [i for i, entity in enumerate(entities) if entity.id == entity_id]
            file, lines = ENTITIES_FILE, entity_lines
        case _:
            return PackError(ENTITIES_FILE, None, None, str(error))
    # A duplicate is reported where it repeats, which is its second table.
    index = indices[1] if len(indices) > 1 else indices[0]
    return PackError(file, lines[index], None, str(error))
