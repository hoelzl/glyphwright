"""The TOML content-pack loader (design 0005, scoping 0003 §8.2).

The loader maps tables one-to-one onto the constructors that already validate
everything; its own job is *location* — every error names the file and the
content object it came from. Syntax errors carry tomllib's line and column;
shape and semantic errors carry file, table, and id.
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
    except (FileNotFoundError, OSError) as error:
        if required:
            raise _fail(name, "pack", "file is missing") from error
        return {}
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise PackError(f"{name}: {error}") from error


def _take(
    file: str, where: str, table: dict[str, Any], allowed: Mapping[str, bool]
) -> dict[str, Any]:
    """Pop exactly the allowed keys; unknown keys and missing required keys
    are shape errors that name their location."""
    taken: dict[str, Any] = {}
    for key, required in allowed.items():
        if key in table:
            taken[key] = table.pop(key)
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
    if not isinstance(entries, list):
        raise _fail(file, where, "modifiers must be an array of tables")
    built = []
    for entry in entries:
        fields = _take(
            file, where, dict(entry), {"stat": True, "op": True, "value": True}
        )
        try:
            built.append(StatModifier(**fields))
        except (ValueError, TypeError) as error:
            raise _fail(file, where, str(error)) from error
    return tuple(built)


def _load_areas(root: Traversable) -> tuple[GridSpace | RoomGraphSpace, ...]:
    file = "areas.toml"
    data = _read(root, file, required=True)
    areas: list[GridSpace | RoomGraphSpace] = []
    for table in data.pop("grid", []):
        fields = _take(file, "grid area", dict(table), {"area": True, "rows": True})
        where = f"grid area {fields['area']!r}"
        try:
            areas.append(GridSpace.from_text(fields["area"], fields["rows"]))
        except (ValueError, TypeError) as error:
            raise _fail(file, where, str(error)) from error
    for table in data.pop("rooms", []):
        table = dict(table)
        area = table.get("area", "?")
        where = f"room area {area!r}"
        fields = _take(file, where, table, {"area": True, "room": True})
        rooms = []
        for room_table in fields["room"]:
            room_fields = _take(
                file,
                where,
                dict(room_table),
                {"id": True, "name": True, "description": True, "exits": False},
            )
            exits = room_fields.pop("exits", {})
            try:
                rooms.append(Room(**room_fields, exits=tuple(sorted(exits.items()))))
            except (ValueError, TypeError) as error:
                raise _fail(file, where, str(error)) from error
        try:
            areas.append(RoomGraphSpace(_area=fields["area"], rooms=tuple(rooms)))
        except ValueError as error:
            raise _fail(file, where, str(error)) from error
    if data:
        raise _fail(file, "areas", f"unknown keys: {', '.join(sorted(data))}")
    return tuple(areas)


def _load_dialogue(file: str, where: str, table: dict[str, Any]) -> Dialogue:
    fields = _take(file, where, dict(table), {"root": True, "node": True})
    nodes = []
    for node_table in fields["node"]:
        node_fields = _take(
            file, where, dict(node_table), {"id": True, "line": True, "choice": True}
        )
        choices = []
        for choice_table in node_fields.pop("choice"):
            choice_fields = _take(
                file,
                where,
                dict(choice_table),
                {"text": True, "next": False, "sets_flag": False},
            )
            choices.append(DialogueChoice(**choice_fields))
        nodes.append(DialogueNode(**node_fields, choices=tuple(choices)))
    try:
        return Dialogue(root=fields["root"], nodes=tuple(nodes))
    except ValueError as error:
        raise _fail(file, where, str(error)) from error


_COMPONENT_KEYS = {
    "id": True,
    "position": False,
    "blocker": False,
    "actor": False,
    "renderable": False,
    "ai": False,
    "portal": False,
    "item": False,
    "consumable": False,
    "equippable": False,
    "openable": False,
    "dialogue": False,
}


def _load_entities(root: Traversable) -> tuple[Entity, ...]:
    file = "entities.toml"
    data = _read(root, file, required=True)
    entities = []
    for table in data.pop("entity", []):
        table = dict(table)
        entity_id = table.get("id", "?")
        where = f"entity {entity_id!r}"
        fields = _take(file, where, table, _COMPONENT_KEYS)
        try:
            entity = _build_entity(file, where, fields)
        except (ValueError, TypeError) as error:
            if isinstance(error, PackError):
                raise
            raise _fail(file, where, str(error)) from error
        entities.append(entity)
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
                "name": True,
                "hp": True,
                "max_hp": True,
                "stats": False,
                "abilities": False,
            },
        )
        stats = actor_fields.pop("stats", {})
        abilities = actor_fields.pop("abilities", [])
        actor = Actor(
            **actor_fields,
            base_stats=tuple(sorted(stats.items())),
            abilities=tuple(abilities),
        )
    renderable = None
    if "renderable" in fields:
        renderable = Renderable(
            **_take(
                file, where, dict(fields["renderable"]), {"glyph": True, "label": True}
            )
        )
    ai = None
    if "ai" in fields:
        ai = AiBehavior(
            **_take(
                file,
                where,
                dict(fields["ai"]),
                {"hostile": False, "engages": False},
            )
        )
    portal = None
    if "portal" in fields:
        portal_fields = _take(
            file, where, dict(fields["portal"]), {"token": True, "to": True}
        )
        portal = Portal(
            token=portal_fields["token"],
            to=_pos(file, where, portal_fields["to"]),
        )
    item = None
    if "item" in fields:
        item = Item(**_take(file, where, dict(fields["item"]), {"name": True}))
    consumable = None
    if "consumable" in fields:
        consumable = Consumable(
            **_take(file, where, dict(fields["consumable"]), {"heal": True})
        )
    equippable = None
    if "equippable" in fields:
        equippable_fields = _take(
            file,
            where,
            dict(fields["equippable"]),
            {"slot": True, "modifiers": False},
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
                {"contains": True, "key": False},
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
        blocker=Blocker() if fields.get("blocker") else None,
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
    for table in data.pop("ability", []):
        table = dict(table)
        where = f"ability {table.get('id', '?')!r}"
        fields = _take(
            file,
            where,
            table,
            {
                "id": True,
                "name": True,
                "targeting": True,
                "effects": True,
                "requires": False,
            },
        )
        effects = []
        for effect_table in fields["effects"]:
            effect_fields = dict(effect_table)
            if "primitive" not in effect_fields:
                raise _fail(file, where, "an effect needs a 'primitive' key")
            primitive = effect_fields.pop("primitive")
            effects.append((primitive, effect_fields))
        requires = fields.get("requires")
        try:
            abilities.append(
                Ability(
                    id=fields["id"],
                    name=fields["name"],
                    targeting=fields["targeting"],
                    effects=tuple(effects),
                    requires_stat=(
                        (str(requires[0]), int(requires[1]))
                        if requires is not None
                        else None
                    ),
                )
            )
        except (ValueError, TypeError, IndexError) as error:
            raise _fail(file, where, str(error)) from error
    statuses = []
    for table in data.pop("status", []):
        table = dict(table)
        where = f"status {table.get('id', '?')!r}"
        fields = _take(
            file, where, table, {"id": True, "name": True, "modifiers": False}
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
    """Load and validate one pack directory; every error names its source."""
    manifest = _read(root, "pack.toml", required=True)
    fields = _take("pack.toml", "manifest", dict(manifest), {"name": True})
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
