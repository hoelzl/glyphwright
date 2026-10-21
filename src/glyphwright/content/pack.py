"""Content packs and their identity.

A pack hashes to a pack id that enters the run fingerprint, so any content
change invalidates recorded baselines, and a verifier can catch "test passed,
but against different data". S1 builds packs in code; the TOML loader arrives
in S2 behind this same type.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from glyphwright.kernel.state import PLAYER
from glyphwright.world.entities import Entity
from glyphwright.world.grid import GridSpace


def _word(owner: str, label: str, value: str) -> None:
    """Ids travel through the command language, which splits on whitespace."""
    if not value or any(ch.isspace() for ch in value):
        raise ValueError(
            f"{owner} {label} {value!r} must be one whitespace-free word: "
            "it travels through the command language"
        )


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
        area_names = [space.area for space in self.areas]
        if len(area_names) != len(set(area_names)):
            raise ValueError("area names must be unique")
        ids = [entity.id for entity in self.entities]
        duplicates = sorted(
            {entity_id for entity_id in ids if ids.count(entity_id) > 1}
        )
        if duplicates:
            # v0 finding L1: a duplicate id silently replaced the earlier entity.
            raise ValueError(f"entity ids must be unique; repeated: {duplicates}")
        for entity in self.entities:
            _word("entity", "id", entity.id)
            if entity.actor is not None and not (
                0 <= entity.actor.hp <= entity.actor.max_hp
            ):
                # v0 finding L2: hp outside its bounds loaded without complaint.
                raise ValueError(
                    f"actor {entity.id!r} has hp {entity.actor.hp} outside "
                    f"0..{entity.actor.max_hp}"
                )

        spaces = {space.area: space for space in self.areas}
        player = next((e for e in self.entities if e.id == PLAYER), None)
        if player is None or player.actor is None or player.at() is None:
            raise ValueError(
                f"a pack must define a {PLAYER!r} entity with an actor and a position"
            )
        for entity in self.entities:
            at = entity.at()
            if at is not None and (
                at.area not in spaces or not spaces[at.area].contains(at)
            ):
                raise ValueError(f"entity {entity.id!r} stands off the map: {at}")

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
