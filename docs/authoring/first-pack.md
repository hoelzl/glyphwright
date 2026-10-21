# Your first pack

A walkthrough from a copy of the reference world to your own playable pack,
including what a load error looks like and how to read it. Read it before you
write your first pack.

## 1. Start from the reference world

A pack is a directory with three files: `pack.toml`, `areas.toml`, and
`entities.toml`. The built-in reference world is one, in
`src/glyphwright/content/packs/reference-vale/`. Copy that directory
somewhere outside the repository, for example to `my-pack/`, and play it:

```bash
uv run glyphwright --pack my-pack
```

## 2. Make it yours

- In `pack.toml`, change `name`. The name becomes part of the pack id, which
  every session records.
- In `areas.toml`, edit the `village` rows: `#` is wall, `.` is floor, and
  every row must be as wide as the first.
- In `entities.toml`, move the player by changing its `position`, written
  `area:x,y` with `x` counting columns from 0 at the left and `y` counting
  rows from 0 at the top.

Every key is described in the [pack format](pack-format.md).

## 3. Connect two areas

The reference world already has two areas, `village` and `warren`, joined by
a portal pair: the `warren-hole` entity in the village leads `down`, and the
`warren-exit` entity in the warren leads `up`. A portal is one-way, so a way
back is a second portal. A portal's token is the word the player types after
`move`, and it may not be `north`, `east`, `south`, or `west` where those are
already exits.

## 4. Read a load error

Break something on purpose, for example set the player's `hp` above its
`max_hp`, and play again:

```text
glyphwright: entities.toml:1: entity 'player': hp 30 is outside 0..20
```

The message names the file, the line of the `[[entity]]` table the problem is
in, the entity, and the rule it breaks. A syntax error also names the column.
The command exits with status 2 and plays nothing, so a script can tell a
broken pack from a finished session.
