"""The TOML content-pack loader (design 0005, scoping 0003 §8.2).

The loader maps tables one-to-one onto the constructors that already validate
everything; its own jobs are *shape* and *location* — every value is checked
against its expected TOML type before a constructor sees it, and every error
names the file and the content object it came from. Syntax errors carry
tomllib's line and column; nothing escapes as a raw traceback.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from importlib.resources.abc import Traversable
from typing import Any

from glyphwright.content.pack import ContentPack
from glyphwright.effects.abilities import Ability, Status
from glyphwright.world.entities import (
    Actor,
    AiBehavior,
    Blocker,
    Consumable,
    Dialogue,
    DialogueChoice,
    DialogueNode,
    Entity,
    Equippable,
    Item,
    Openable,
    Portal,
    Position,
    Renderable,
    StatModifier,
)
from glyphwright.world.grid import GridSpace
from glyphwright.world.roomgraph import Room, RoomGraphSpace
from glyphwright.world.space import PosId


class PackError(ValueError):
    """A content-pack problem, located: file, object, and what went wrong."""


def _fail(file: str, where: str, problem: str) -> PackError:
    return PackError(f"{file}: {where}: {problem}")


def _read(root: Traversable, name: str, *, required: bool) -> dict[str, Any]:
    resource = root / name
    try:
        text = resource.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        if required:
            raise PackError(
                f"{name}: file is missing — is {str(root)!r} a pack directory?"
            ) from error
        return {}
    except UnicodeDecodeError as error:
        raise PackError(f"{name}: not valid UTF-8 ({error})") from error
    except OSError as error:
        # Unreadable is never "absent": permission problems and
        # file-vs-directory confusions must not silently drop content.
        raise PackError(f"{name}: cannot read ({error})") from error
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise PackError(f"{name}: {error}") from error


def _tables(file: str, where: str, value: Any) -> list[dict[str, Any]]:
    """An array of tables (``[[x]]``), each copied for consumption."""
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise _fail(file, where, "expected an array of tables ([[...]], not [...])")
    return [dict(item) for item in value]


def _table(file: str, where: str, key: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _fail(file, where, f"{key!r} must be a table")
    return dict(value)


def _typed(file: str, where: str, key: str, value: Any, expected: type) -> Any:
    ok = isinstance(value, expected)
    if expected is int and isinstance(value, bool):
        ok = False  # bool is an int in Python; not in content
    if not ok:
        raise _fail(
            file,
            where,
            f"{key!r} must be {expected.__name__}, got {value!r}",
        )
    return value


def _take(
    file: str,
    where: str,
    table: dict[str, Any],
    spec: Mapping[str, tuple[bool, type | None]],
) -> dict[str, Any]:
    """Pop exactly the allowed keys, type-checking scalars as they come.

    Unknown keys, missing required keys, and wrong-typed values are shape
    errors that name their location (design 0005 §3 layer 2).
    """
    taken: dict[str, Any] = {}
    for key, (required, expected) in spec.items():
        if key in table:
            value = table.pop(key)
            if expected is not None:
                value = _typed(file, where, key, value, expected)
            taken[key] = value
        elif required:
            raise _fail(file, where, f"missing required key {key!r}")
    if table:
        unknown = ", ".join(sorted(table))
        raise _fail(file, where, f"unknown keys: {unknown}")
    return taken


def _pos(file: str, where: str, text: Any) -> PosId:
    if not isinstance(text, str):
        raise _fail(file, where, "position must be an 'area:local' string")
    try:
        return PosId.parse(text)
    except ValueError as error:
        raise _fail(file, where, str(error)) from error


def _modifiers(file: str, where: str, entries: Any) -> tuple[StatModifier, ...]:
    built = []
    for entry in _tables(file, where, entries):
        fields = _take(
            file,
            where,
            entry,
            {"stat": (True, str), "op": (True, str), "value": (True, int)},
        )
        try:
            built.append(StatModifier(**fields))
        except ValueError as error:
            raise _fail(file, where, str(error)) from error
    return tuple(built)


def _int_mapping(
    file: str, where: str, key: str, value: Any
) -> tuple[tuple[str, int], ...]:
    entries = _table(file, where, key, value)
    for name, number in entries.items():
        _typed(file, where, f"{key}.{name}", number, int)
    return tuple(sorted(entries.items()))


def _load_areas(root: Traversable) -> tuple[GridSpace | RoomGraphSpace, ...]:
    file = "areas.toml"
    data = _read(root, file, required=True)
    areas: list[GridSpace | RoomGraphSpace] = []
    for table in _tables(file, "grid areas", data.pop("grid", [])):
        fields = _take(
            file,
            "grid area",
            table,
            {"area": (True, str), "rows": (True, str), "fov": (False, int)},
        )
        where = f"grid area {fields['area']!r}"
        fov = fields.get("fov", 0)
        if fov < 0:
            raise _fail(file, where, "fov must be 0 (omniscient) or a positive radius")
        try:
            areas.append(GridSpace.from_text(fields["area"], fields["rows"], fov=fov))
        except ValueError as error:
            raise _fail(file, where, str(error)) from error
    for table in _tables(file, "room areas", data.pop("rooms", [])):
        area = table.get("area", "?")
        where = f"room area {area!r}"
        fields = _take(file, where, table, {"area": (True, str), "room": (True, list)})
        rooms = []
        for room_table in _tables(file, where, fields["room"]):
            room_id = room_table.get("id", "?")
            room_where = f"{where} room {room_id!r}"
            room_fields = _take(
                file,
                room_where,
                room_table,
                {
                    "id": (True, str),
                    "name": (True, str),
                    "description": (True, str),
                    "exits": (False, dict),
                },
            )
            exits = room_fields.pop("exits", {})
            for token, destination in exits.items():
                _typed(file, room_where, f"exits.{token}", destination, str)
            try:
                rooms.append(Room(**room_fields, exits=tuple(sorted(exits.items()))))
            except ValueError as error:
                raise _fail(file, room_where, str(error)) from error
        try:
            areas.append(RoomGraphSpace(_area=fields["area"], rooms=tuple(rooms)))
        except ValueError as error:
            raise _fail(file, where, str(error)) from error
    if data:
        raise _fail(file, "areas", f"unknown keys: {', '.join(sorted(data))}")
    return tuple(areas)


def _load_dialogue(file: str, where: str, value: Any) -> Dialogue:
    fields = _take(
        file,
        where,
        _table(file, where, "dialogue", value),
        {"root": (True, str), "node": (True, list)},
    )
    nodes = []
    for node_table in _tables(file, where, fields["node"]):
        node_id = node_table.get("id", "?")
        node_where = f"{where} dialogue node {node_id!r}"
        node_fields = _take(
            file,
            node_where,
            node_table,
            {"id": (True, str), "line": (True, str), "choice": (True, list)},
        )
        choices = []
        for choice_table in _tables(file, node_where, node_fields.pop("choice")):
            choice_fields = _take(
                file,
                node_where,
                choice_table,
                {
                    "text": (True, str),
                    "next": (False, str),
                    "sets_flag": (False, str),
                },
            )
            choices.append(DialogueChoice(**choice_fields))
        nodes.append(DialogueNode(**node_fields, choices=tuple(choices)))
    try:
        return Dialogue(root=fields["root"], nodes=tuple(nodes))
    except ValueError as error:
        raise _fail(file, where, str(error)) from error


# The engine narrates battle placement and homecoming through these exit
# tokens on Moved events; a content portal claiming one would make a plain
# walk read as a battle transition.
_RESERVED_EXIT_TOKENS = frozenset({"arena", "return"})

_COMPONENT_SPEC: dict[str, tuple[bool, type | None]] = {
    "id": (True, str),
    "position": (False, str),
    "blocker": (False, bool),
    "actor": (False, dict),
    "renderable": (False, dict),
    "ai": (False, dict),
    "portal": (False, dict),
    "item": (False, dict),
    "consumable": (False, dict),
    "equippable": (False, dict),
    "openable": (False, dict),
    "dialogue": (False, dict),
}


def _load_entities(root: Traversable) -> tuple[Entity, ...]:
    file = "entities.toml"
    data = _read(root, file, required=True)
    entities = []
    for table in _tables(file, "entities", data.pop("entity", [])):
        entity_id = table.get("id", "?")
        where = f"entity {entity_id!r}"
        fields = _take(file, where, table, _COMPONENT_SPEC)
        entities.append(_build_entity(file, where, fields))
    if data:
        raise _fail(file, "entities", f"unknown keys: {', '.join(sorted(data))}")
    return tuple(entities)


def _build_entity(file: str, where: str, fields: dict[str, Any]) -> Entity:
    actor = None
    if "actor" in fields:
        actor_fields = _take(
            file,
            where,
            dict(fields["actor"]),
            {
                "name": (True, str),
                "hp": (True, int),
                "max_hp": (True, int),
                "stats": (False, dict),
                "abilities": (False, list),
            },
        )
        stats = _int_mapping(file, where, "stats", actor_fields.pop("stats", {}))
        abilities = actor_fields.pop("abilities", [])
        for ability in abilities:
            _typed(file, where, "abilities entry", ability, str)
        actor = Actor(**actor_fields, base_stats=stats, abilities=tuple(abilities))
    renderable = None
    if "renderable" in fields:
        renderable_fields = _take(
            file,
            where,
            dict(fields["renderable"]),
            {"glyph": (True, str), "label": (True, str)},
        )
        if renderable_fields["glyph"] == "?":
            raise _fail(file, where, "the glyph '?' is reserved for unseen tiles")
        renderable = Renderable(**renderable_fields)
    ai = None
    if "ai" in fields:
        ai = AiBehavior(
            **_take(
                file,
                where,
                dict(fields["ai"]),
                {
                    "hostile": (False, bool),
                    "engages": (False, bool),
                    "arena": (False, str),
                },
            )
        )
    portal = None
    if "portal" in fields:
        portal_fields = _take(
            file,
            where,
            dict(fields["portal"]),
            {"token": (True, str), "to": (True, str)},
        )
        if portal_fields["token"] in _RESERVED_EXIT_TOKENS:
            raise _fail(
                file,
                where,
                f"the portal token {portal_fields['token']!r} is reserved "
                "for battle transitions",
            )
        portal = Portal(
            token=portal_fields["token"],
            to=_pos(file, where, portal_fields["to"]),
        )
    item = None
    if "item" in fields:
        item = Item(**_take(file, where, dict(fields["item"]), {"name": (True, str)}))
    consumable = None
    if "consumable" in fields:
        consumable = Consumable(
            **_take(file, where, dict(fields["consumable"]), {"heal": (True, int)})
        )
    equippable = None
    if "equippable" in fields:
        equippable_fields = _take(
            file,
            where,
            dict(fields["equippable"]),
            {"slot": (True, str), "modifiers": (False, list)},
        )
        equippable = Equippable(
            slot=equippable_fields["slot"],
            modifiers=_modifiers(file, where, equippable_fields.get("modifiers", [])),
        )
    openable = None
    if "openable" in fields:
        openable = Openable(
            **_take(
                file,
                where,
                dict(fields["openable"]),
                {"contains": (True, str), "key": (False, str)},
            )
        )
    dialogue = None
    if "dialogue" in fields:
        dialogue = _load_dialogue(file, where, fields["dialogue"])

    return Entity(
        id=fields["id"],
        position=(
            Position(at=_pos(file, where, fields["position"]))
            if "position" in fields
            else None
        ),
        actor=actor,
        blocker=Blocker() if fields.get("blocker", False) else None,
        renderable=renderable,
        ai=ai,
        portal=portal,
        dialogue=dialogue,
        openable=openable,
        item=item,
        consumable=consumable,
        equippable=equippable,
    )


def _load_abilities(
    root: Traversable,
) -> tuple[tuple[Ability, ...], tuple[Status, ...]]:
    file = "abilities.toml"
    data = _read(root, file, required=False)
    abilities = []
    for table in _tables(file, "abilities", data.pop("ability", [])):
        where = f"ability {table.get('id', '?')!r}"
        fields = _take(
            file,
            where,
            table,
            {
                "id": (True, str),
                "name": (True, str),
                "targeting": (True, str),
                "effects": (True, list),
                "requires": (False, list),
            },
        )
        effects = []
        for effect_table in _tables(file, where, fields["effects"]):
            if "primitive" not in effect_table:
                raise _fail(file, where, "an effect needs a 'primitive' key")
            primitive = _typed(
                file, where, "primitive", effect_table.pop("primitive"), str
            )
            effects.append((primitive, effect_table))
        requires = fields.get("requires")
        requires_stat = None
        if requires is not None:
            if (
                len(requires) != 2
                or not isinstance(requires[0], str)
                or not isinstance(requires[1], int)
                or isinstance(requires[1], bool)
            ):
                raise _fail(file, where, "'requires' must be [stat-name, minimum]")
            requires_stat = (requires[0], requires[1])
        try:
            abilities.append(
                Ability(
                    id=fields["id"],
                    name=fields["name"],
                    targeting=fields["targeting"],
                    effects=tuple(effects),
                    requires_stat=requires_stat,
                )
            )
        except ValueError as error:
            raise _fail(file, where, str(error)) from error
    statuses = []
    for table in _tables(file, "statuses", data.pop("status", [])):
        where = f"status {table.get('id', '?')!r}"
        fields = _take(
            file,
            where,
            table,
            {"id": (True, str), "name": (True, str), "modifiers": (False, list)},
        )
        statuses.append(
            Status(
                id=fields["id"],
                name=fields["name"],
                modifiers=_modifiers(file, where, fields.get("modifiers", [])),
            )
        )
    if data:
        raise _fail(file, "abilities", f"unknown keys: {', '.join(sorted(data))}")
    return tuple(abilities), tuple(statuses)


def load_pack(root: Traversable) -> ContentPack:
    """Load and validate one pack directory; every error names its source.

    Nothing escapes as a raw traceback: unforeseen shapes are still wrapped
    as :class:`PackError`, because the CLI's clean-diagnostic contract must
    hold for content nobody anticipated.
    """
    try:
        manifest = _read(root, "pack.toml", required=True)
        fields = _take("pack.toml", "manifest", dict(manifest), {"name": (True, str)})
        areas = _load_areas(root)
        entities = _load_entities(root)
        abilities, statuses = _load_abilities(root)
        try:
            return ContentPack(
                name=fields["name"],
                areas=areas,
                entities=entities,
                abilities=abilities,
                statuses=statuses,
            )
        except ValueError as error:
            raise PackError(f"pack {fields['name']!r}: {error}") from error
    except PackError:
        raise
    except Exception as error:  # pragma: no cover - the safety net
        raise PackError(f"{str(root)!r}: malformed pack: {error}") from error
