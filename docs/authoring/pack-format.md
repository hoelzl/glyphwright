# Pack format

Every file, table, and key a content pack may contain, with the rules each one
must follow. Read it while you write or debug a pack; a test checks that every
key the loader accepts is listed here.

## Contents

- [Files](#files)
- [pack.toml](#packtoml)
- [areas.toml](#areastoml)
- [entities.toml](#entitiestoml)
- [Rules across the pack](#rules-across-the-pack)
- [Not supported yet](#not-supported-yet)

## Files

A pack is a directory with exactly three TOML files, encoded as UTF-8:
`pack.toml`, `areas.toml`, and `entities.toml`. Files that do not end in
`.toml` are ignored; any other `.toml` file is an error.

## pack.toml

| Key | Type | Required | Meaning |
|---|---|---|---|
| `name` | string | yes | the pack's name; part of its pack id |

## areas.toml

One `[[grid]]` table per area.

| Key | Type | Required | Meaning |
|---|---|---|---|
| `area` | string | yes | the area's name: one word, no `:` |
| `rows` | string | yes | the map, one line per row: `#` wall, `.` floor; all rows equally wide |

## entities.toml

One `[[entity]]` table per entity. An entity is an id plus optional parts.

| Key | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | unique, one word without `.`; not `world`; the id `player` is the protagonist |
| `position` | string | no | where it stands: `area:x,y`, for example `village:1,1` |
| `blocker` | boolean | no | `true` if nothing else may enter its tile |

**`actor`** (`[entity.actor]`): something that takes turns and shows in frames.

| Key | Type | Required | Meaning |
|---|---|---|---|
| `name` | string | yes | display name |
| `hp` | integer | yes | current hit points, from 0 to `max_hp` |
| `max_hp` | integer | yes | maximum hit points |
| `stats` | table | no | base stats, such as `{ atk = 5, def = 3 }`; names are one word without `.` |

**`renderable`** (`[entity.renderable]`): how the entity is drawn.

| Key | Type | Required | Meaning |
|---|---|---|---|
| `glyph` | string | yes | one visible character, not `#` or `.` |
| `label` | string | yes | what the glyph means, shown in the legend |

**`portal`** (`[entity.portal]`): a one-way way out of the tile the entity stands on.

| Key | Type | Required | Meaning |
|---|---|---|---|
| `token` | string | yes | the word after `move`, such as `down` |
| `to` | string | yes | the destination, `area:x,y` |

**`item`** (`[entity.item]`): something the player can take.

| Key | Type | Required | Meaning |
|---|---|---|---|
| `name` | string | yes | display name |

**`consumable`** (`[entity.consumable]`): an item used up by `use`.

| Key | Type | Required | Meaning |
|---|---|---|---|
| `heal` | integer | yes | hit points restored, at least 1 |

**`equippable`** (`[entity.equippable]`): an item worn with `equip`.

| Key | Type | Required | Meaning |
|---|---|---|---|
| `slot` | string | yes | the slot it fills, such as `weapon`; one word without `.` |
| `modifiers` | array of tables | no | what it does to stats while worn |

Each entry of `modifiers` is a table:

| Key | Type | Required | Meaning |
|---|---|---|---|
| `stat` | string | yes | the stat it changes |
| `op` | string | yes | `add` adds `value`; `mul` multiplies by `value` percent |
| `value` | integer | yes | the amount; a `mul` value is 0 or more (150 means +50%) |

All `add` modifiers apply before any `mul` one, and a stat never drops below
zero.

## Rules across the pack

- There is exactly one entity with id `player`, and it has an actor and a
  position.
- Positions use the exact form `area:x,y`: no spaces, no leading zeros.
- Every positioned entity stands on a floor tile of an existing area.
- At most one blocker stands on a tile.
- One glyph has one label across the pack.
- A portal stands somewhere, is neither an actor nor a blocker, leads to a
  floor tile, and its token is not already an exit of its tile.
- A `consumable` or `equippable` entity is also an `item`. An item has a
  position and is not an actor, a blocker, or a portal.

## Not supported yet

These parts of the format arrive with later slices. A pack that uses them
fails with "is not supported by this engine version":

- the files `abilities.toml`, `presentation.toml`, and `tileset.toml`;
- `rooms` areas (`[[rooms]]`) and the grid key `fov`;
- the entity parts `ai`, `openable`, and `dialogue`;
- the actor keys `mp`, `max_mp`, `abilities`, and `perks`;
- the consumable key `mana`.
