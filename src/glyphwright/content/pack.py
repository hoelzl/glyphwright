"""Content packs and their identity.

A pack hashes to a pack id that enters the run fingerprint, so any content
change invalidates recorded baselines and TermVerify can catch "test passed, but
against different data" (design 0003 section 8.2).

Slice 1 ships one built-in reference pack. TOML loading, schema validation, and
file/line diagnostics arrive with the content-driven slices; the hashing and
identity contract is established here so the fingerprint is real from day one.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass

from glyphwright.effects.abilities import Ability, Status
from glyphwright.world.entities import (
    Entity,
)
from glyphwright.world.grid import GridSpace
from glyphwright.world.roomgraph import RoomGraphSpace


@dataclass(frozen=True, slots=True)
class ContentPack:
    """Validated content plus the hash that identifies it.

    Construction validates the cross-area wiring — a portal must stand on a
    real position, lead to a real position, and neither shadow a geometric
    exit nor collide with another portal — because a load-time diagnostic
    beats a mid-session crash (0003 §8.2).
    """

    name: str
    areas: tuple[GridSpace | RoomGraphSpace, ...]
    entities: tuple[Entity, ...]
    abilities: tuple[Ability, ...] = ()
    statuses: tuple[Status, ...] = ()

    def __post_init__(self) -> None:
        from glyphwright.effects.primitives import PRIMITIVES, validate_params

        # The kernel's preconditions, promised at load rather than discovered
        # mid-session: a playable protagonist, and every position on the map.
        spaces_by_area = {space.area: space for space in self.areas}
        player = next(
            (entity for entity in self.entities if entity.id == "player"), None
        )
        if player is None or player.actor is None or player.at() is None:
            raise ValueError(
                "a pack must define a 'player' entity with an actor and a position"
            )
        for entity in self.entities:
            at = entity.at()
            if at is None:
                continue
            if at.area not in spaces_by_area or not spaces_by_area[at.area].contains(
                at
            ):
                raise ValueError(f"entity {entity.id!r} stands off the map: {at}")

        ability_ids = {ability.id for ability in self.abilities}
        status_ids = {status.id for status in self.statuses}
        if len(ability_ids) != len(self.abilities):
            raise ValueError("ability ids must be unique")
        if len(status_ids) != len(self.statuses):
            raise ValueError("status ids must be unique")

        def check_effects(
            owner: str, effects: tuple[tuple[str, Mapping[str, object]], ...]
        ) -> None:
            """One rule for every effect chain, ability or hook alike."""
            for name, params in effects:
                if name not in PRIMITIVES:
                    raise ValueError(f"{owner} names unknown primitive {name!r}")
                try:
                    validate_params(name, params)
                except ValueError as error:
                    raise ValueError(f"{owner}: {error}") from error
                if name == "apply_status" and params.get("status") not in status_ids:
                    raise ValueError(
                        f"{owner} applies unknown status {params.get('status')!r}"
                    )
                if name == "grant_perk" and params.get("perk") not in status_ids:
                    raise ValueError(
                        f"{owner} grants unknown perk {params.get('perk')!r} "
                        "(a perk is a status definition)"
                    )

        for ability in self.abilities:
            check_effects(f"ability {ability.id!r}", ability.effects)
        for status in self.statuses:
            for hook in status.hooks:
                check_effects(f"status {status.id!r} hook on {hook.on!r}", hook.effects)
        for entity in self.entities:
            if entity.actor is not None:
                for ability_id in entity.actor.abilities:
                    if ability_id not in ability_ids:
                        raise ValueError(
                            f"actor {entity.id!r} knows unknown ability {ability_id!r}"
                        )
                for perk_id in entity.actor.perks:
                    if perk_id not in status_ids:
                        raise ValueError(
                            f"actor {entity.id!r} bears unknown perk {perk_id!r} "
                            "(a perk is a status definition)"
                        )
        spaces = {space.area: space for space in self.areas}
        if len(spaces) != len(self.areas):
            raise ValueError("area ids must be unique")
        ids = {entity.id for entity in self.entities}
        for entity in self.entities:
            openable = entity.openable
            if openable is not None:
                # A chest that references nothing crashes the fold mid-open;
                # a mistyped key silently forces the minigame. Both are
                # load-time diagnostics.
                if openable.contains not in ids:
                    raise ValueError(
                        f"openable {entity.id!r} contains unknown entity "
                        f"{openable.contains!r}"
                    )
                if openable.key is not None and openable.key not in ids:
                    raise ValueError(
                        f"openable {entity.id!r} answers to unknown key "
                        f"{openable.key!r}"
                    )
        checked_arenas: set[str] = set()
        for entity in self.entities:
            ai = entity.ai
            if ai is None or ai.arena is None:
                continue
            # An arena must be a grid with no back doors: flee is the exit
            # (design 0006 §2).
            arena_space = spaces.get(ai.arena)
            if not isinstance(arena_space, GridSpace):
                raise ValueError(
                    f"actor {entity.id!r} names arena {ai.arena!r}, which is "
                    "not a grid area"
                )
            if ai.arena not in checked_arenas:
                checked_arenas.add(ai.arena)
                for other in self.entities:
                    if (
                        other.portal is not None
                        and (at := other.at()) is not None
                        and at.area == ai.arena
                    ):
                        raise ValueError(
                            f"arena {ai.arena!r} contains portal {other.id!r}; "
                            "a battlefield has no back doors"
                        )
            # ... and must seat the largest battle the authored positions can
            # open: the player plus every hostile in the engager's home area
            # (the possible joiners). Battles that outgrow it at runtime fall
            # back to the menu presentation.
            home = entity.at()
            seats = 1 + sum(
                1
                for other in self.entities
                if other.ai is not None
                and other.ai.hostile
                and home is not None
                and (other_at := other.at()) is not None
                and other_at.area == home.area
            )
            floors = sum(
                1 for pos in arena_space.positions() if arena_space.terrain(pos) != "#"
            )
            if floors < seats:
                raise ValueError(
                    f"arena {ai.arena!r} has {floors} floor tiles but a battle "
                    f"opened by {entity.id!r} may draw {seats} combatants"
                )
        claimed: set[tuple[str, str]] = set()
        for entity in self.entities:
            portal = entity.portal
            if portal is None:
                continue
            at = entity.at()
            if at is None:
                raise ValueError(f"portal {entity.id!r} stands nowhere")
            if at.area not in spaces or not spaces[at.area].contains(at):
                raise ValueError(f"portal {entity.id!r} stands off the map: {at}")
            if portal.to.area not in spaces or not spaces[portal.to.area].contains(
                portal.to
            ):
                raise ValueError(f"portal {entity.id!r} leads nowhere: {portal.to}")
            if portal.token in spaces[at.area].exits(at):
                raise ValueError(
                    f"portal {entity.id!r} token {portal.token!r} shadows a "
                    f"geometric exit at {at}"
                )
            key = (str(at), portal.token)
            if key in claimed:
                raise ValueError(
                    f"two portals at {at} claim the token {portal.token!r}"
                )
            claimed.add(key)

    @property
    def pack_id(self) -> str:
        """A stable ``name@sha256:…`` identifier over canonical content.

        Hashing walks every field via ``asdict``, so adding a component or an
        area kind automatically widens the identity — a pack cannot change
        content without changing its id.
        """

        def canonical_area(space: GridSpace | RoomGraphSpace) -> dict[str, object]:
            fields = asdict(space)
            fields["area"] = fields.pop("_area")
            fields["kind"] = type(space).__name__
            return fields

        payload = json.dumps(
            {
                "name": self.name,
                "areas": [canonical_area(space) for space in self.areas],
                "abilities": [asdict(ability) for ability in self.abilities],
                "statuses": [asdict(status) for status in self.statuses],
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


def reference_pack() -> ContentPack:
    """The built-in pack, loaded from its packaged TOML files.

    One source of truth: the same loader that serves external packs serves
    this one, so the whole test suite exercises it (design 0005 §4).
    """
    from importlib.resources import files

    from glyphwright.content.loader import load_pack

    return load_pack(files("glyphwright.content") / "packs" / "reference-vale")
