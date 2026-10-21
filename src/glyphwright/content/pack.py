"""Content packs and their identity.

A pack hashes to a pack id that enters the run fingerprint, so any content
change invalidates recorded baselines, and a verifier can catch "test passed,
but against different data". The TOML loader builds packs; tests may build
them in code.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from glyphwright.kernel.state import PLAYER
from glyphwright.world.entities import Entity
from glyphwright.world.grid import FLOOR, WALL, GridSpace
from glyphwright.world.space import PosId

Subject = tuple[str, str]


class ContentError(ValueError):
    """Content that breaks a load-time rule.

    ``subject`` names what the rule is about, such as ``("entity",
    "goblin-1")`` or ``("area", "village")``, so the TOML loader can point at
    the table that defines it.
    """

    def __init__(self, subject: Subject | None, message: str) -> None:
        super().__init__(message)
        self.subject = subject


def _entity(entity: Entity, message: str) -> ContentError:
    return ContentError(("entity", entity.id), f"entity {entity.id!r}: {message}")


def _word(subject: Subject, label: str, value: str) -> None:
    """Ids travel through the command language, which splits on whitespace."""
    if not value or any(ch.isspace() for ch in value):
        raise ContentError(
            subject,
            f"{label} {value!r} must be one whitespace-free word: it travels "
            "through the command language",
        )


def _name(subject: Subject, label: str, value: str) -> None:
    """Stat names and slots appear in :query paths, which split on '.'."""
    _word(subject, label, value)
    if "." in value:
        # v2 finding N12.
        raise ContentError(subject, f"{label} {value!r} may not contain '.'")


RESERVED_ID = "world"


@dataclass(frozen=True, slots=True)
class ContentPack:
    """Validated content plus the hash that identifies it.

    Construction checks the kernel's preconditions, because a load-time
    diagnostic beats a mid-session crash.
    """

    name: str
    areas: tuple[GridSpace, ...]
    entities: tuple[Entity, ...]

    def __post_init__(self) -> None:
        self._check_areas()
        self._check_entities()
        self._check_placement()
        self._check_portals()
        self._check_items()
        self._check_ai()

    def _check_areas(self) -> None:
        seen: set[str] = set()
        for space in self.areas:
            subject = ("area", space.area)
            _word(subject, "area name", space.area)
            if ":" in space.area:
                # v2 finding N2: a ':' would break every position identifier.
                raise ContentError(subject, f"area name {space.area!r} contains ':'")
            if space.area in seen:
                raise ContentError(subject, f"area {space.area!r} is defined twice")
            seen.add(space.area)

    def _check_entities(self) -> None:
        seen: set[str] = set()
        labels: dict[str, str] = {}
        for entity in self.entities:
            _word(("entity", entity.id), "entity id", entity.id)
            if "." in entity.id or entity.id == RESERVED_ID:
                # v2 finding N8: :query splits paths on '.', and 'world' names
                # the world itself, so such an entity could never be queried.
                raise _entity(entity, f"ids may not contain '.' or be {RESERVED_ID!r}")
            if entity.id in seen:
                # v0 finding L1: a duplicate id silently replaced the earlier one.
                raise _entity(entity, "is defined twice; entity ids must be unique")
            seen.add(entity.id)
            actor = entity.actor
            if actor is not None and not 0 <= actor.hp <= actor.max_hp:
                # v0 finding L2: hp outside its bounds loaded without complaint.
                raise _entity(entity, f"hp {actor.hp} is outside 0..{actor.max_hp}")
            renderable = entity.renderable
            if renderable is not None:
                glyph = renderable.glyph
                if len(glyph) != 1 or glyph.isspace() or glyph in (FLOOR, WALL):
                    raise _entity(
                        entity,
                        f"glyph {glyph!r} must be one visible character other "
                        f"than {FLOOR!r} and {WALL!r}",
                    )
                if labels.setdefault(glyph, renderable.label) != renderable.label:
                    # v2 finding N3: the legend holds one label per glyph.
                    raise _entity(
                        entity,
                        f"glyph {glyph!r} already means {labels[glyph]!r}, "
                        f"not {renderable.label!r}",
                    )
        player = next((e for e in self.entities if e.id == PLAYER), None)
        if player is None or player.actor is None or player.at() is None:
            raise ContentError(
                None,
                f"a pack must define a {PLAYER!r} entity with an actor and a position",
            )

    def _check_placement(self) -> None:
        spaces = {space.area: space for space in self.areas}
        blocked: dict[PosId, str] = {}
        for entity in self.entities:
            at = entity.at()
            if at is None:
                continue
            if at.area not in spaces or not spaces[at.area].contains(at):
                # v2 finding N1: contains() accepts only the canonical spelling.
                raise _entity(entity, f"stands off the map: {at}")
            if spaces[at.area].terrain(at) != FLOOR:
                # v2 finding N4: nothing may stand inside a wall.
                raise _entity(entity, f"stands in a wall: {at}")
            if entity.blocker is not None:
                if at in blocked:
                    # v2 finding N5: two blockers on one tile.
                    raise _entity(
                        entity, f"blocks {at}, already blocked by {blocked[at]!r}"
                    )
                blocked[at] = entity.id

    def _check_portals(self) -> None:
        spaces = {space.area: space for space in self.areas}
        claimed: set[tuple[PosId, str]] = set()
        for entity in self.entities:
            portal = entity.portal
            if portal is None:
                continue
            _word(("entity", entity.id), "portal token", portal.token)
            at = entity.at()
            if at is None:
                raise _entity(entity, "is a portal that stands nowhere")
            if entity.actor is not None or entity.blocker is not None:
                # A portal must stay put and stay enterable: an actor could
                # carry it onto a geometric exit, and a blocker hides it.
                raise _entity(entity, "a portal cannot be an actor or a blocker")
            to = portal.to
            if to.area not in spaces or not spaces[to.area].contains(to):
                raise _entity(entity, f"portal leads nowhere: {to}")
            if spaces[to.area].terrain(to) != FLOOR:
                raise _entity(entity, f"portal leads into a wall: {to}")
            if portal.token in spaces[at.area].exits(at):
                # v0 finding K10: the token would silently shadow that exit.
                raise _entity(
                    entity,
                    f"portal token {portal.token!r} shadows a geometric exit at {at}",
                )
            if (at, portal.token) in claimed:
                raise _entity(
                    entity, f"another portal at {at} already claims {portal.token!r}"
                )
            claimed.add((at, portal.token))

    def _check_items(self) -> None:
        for entity in self.entities:
            subject = ("entity", entity.id)
            if entity.actor is not None:
                for stat, _ in entity.actor.base_stats:
                    _name(subject, "stat name", stat)
            if (entity.consumable or entity.equippable) and entity.item is None:
                # v2 finding N7: only items can be carried and used.
                raise _entity(entity, "a consumable or equippable must be an item")
            if entity.item is not None:
                if entity.at() is None:
                    raise _entity(entity, "an item must have a position")
                if entity.actor or entity.blocker or entity.portal:
                    # v2 finding N7: taking one would corrupt the world.
                    raise _entity(
                        entity, "an item cannot be an actor, a blocker, or a portal"
                    )
            if entity.consumable is not None and entity.consumable.heal < 1:
                # v0 finding K5: a negative heal drove hp below zero.
                raise _entity(entity, "a consumable must heal at least 1 hp")
            if entity.equippable is not None:
                _name(subject, "slot", entity.equippable.slot)
                for modifier in entity.equippable.modifiers:
                    _name(subject, "stat name", modifier.stat)

    def _check_ai(self) -> None:
        for entity in self.entities:
            if entity.ai is None:
                continue
            if entity.id == PLAYER:
                raise _entity(entity, "the player cannot have an ai")
            if entity.actor is None or entity.at() is None:
                raise _entity(entity, "an ai must be a placed actor")
            if not entity.ai.hostile:
                # A friendly ai would load and then do nothing at all.
                raise _entity(entity, "only hostile ai is supported by this engine")

    @property
    def pack_id(self) -> str:
        """A stable ``name@sha256:…`` identifier over canonical content.

        Hashing walks every field via ``asdict``, so adding a component widens
        the identity automatically: a pack cannot change content without
        changing its id.
        """

        def canonical_area(space: GridSpace) -> dict[str, object]:
            fields = asdict(space)
            fields["area"] = fields.pop("_area")
            fields["kind"] = type(space).__name__
            return fields

        payload = json.dumps(
            {
                "name": self.name,
                "areas": [canonical_area(space) for space in self.areas],
                "entities": [
                    asdict(entity)
                    for entity in sorted(self.entities, key=lambda e: e.id)
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return f"{self.name}@sha256:{digest}"
