"""Populating the oracle fingerprint from a live editor (design 0012 §6, 15A).

``glyphwright.session/2`` carries an *optional* :class:`OracleFingerprint` for
Tier-2 runs — the coarse identity of the UE5 oracle a run consulted. The three
terms are populated here from a live :class:`UE5Client`:

- ``level`` — the loaded map's path (``current_level``).
- ``plugin`` — the AgentWorld toolset's reported ``version`` (``describe_toolset``).
- ``positions`` — a ``sha256:`` over the sorted set of bound semantic-position
  keys (the anchors' ``worldStateKey``), so the fingerprint changes exactly
  when the set of addressable positions changes.

Deliberately coarse: it answers "same map, same plugin build, same set of
semantic positions?" and nothing more. Collision-geometry drift is *not*
encoded here — that is the drift-detection audit's job (0012 §11.5). Only
:func:`oracle_fingerprint` touches the network; the key-hashing is pure.
"""

from __future__ import annotations

import hashlib

from glyphwright.frontends.presentation.ue5.client import ANCHOR, UE5Client
from glyphwright.harness.fingerprint import OracleFingerprint


def positions_fingerprint(world_state_keys: list[str]) -> str:
    """A stable ``sha256:`` over the set of bound semantic-position keys.

    Sorted before hashing so the fingerprint depends on the *set* of keys, not
    the order the editor happened to report them. Pure.
    """
    canonical = "\n".join(sorted(set(world_state_keys)))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def oracle_fingerprint(client: UE5Client) -> OracleFingerprint:
    """Build the coarse oracle fingerprint from a live editor session.

    ``positions`` hashes the anchors' ``worldStateKey`` set — the bound
    semantic positions the oracle can address. An anchor without a
    ``worldStateKey`` contributes nothing (it binds no position).
    """
    level = await client.current_level()
    descriptor = await client.describe_toolset(ANCHOR)
    plugin = str(descriptor["version"])
    anchors = await client.list_anchors()
    keys = [str(a["worldStateKey"]) for a in anchors if a.get("worldStateKey")]
    return OracleFingerprint(
        level=level, plugin=plugin, positions=positions_fingerprint(keys)
    )
