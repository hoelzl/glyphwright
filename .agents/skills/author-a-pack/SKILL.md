---
name: author-a-pack
description: Write or fix a GlyphWright content pack (TOML areas, entities, items, hostiles, portals) and read its located load diagnostics. Use when you create a world, change a pack, or a pack fails to load.
---

# Author a pack

## 1. Start from the reference world

A pack is a directory with `pack.toml`, `areas.toml`, and `entities.toml`.
Copy the reference world next to the repository, not into it:

```bash
cp -r src/glyphwright/content/packs/reference-vale ../my-pack
```

Set `name` in `../my-pack/pack.toml`, and pass `--pack ../my-pack` below. Every key, table, and rule is in the
[pack format](../../../docs/authoring/pack-format.md); the guided walkthrough is
[your first pack](../../../docs/authoring/first-pack.md).

## 2. Change one thing at a time

After each change, load the pack:

```bash
uv run glyphwright --pack ../my-pack
```

- **Areas** are grids of `#` and `.`; every row is equally wide.
- **Entities** need a unique `id`; the `player` needs an actor and a position.
- **Two areas** connect with a `portal` entity on each side.
- **Items** have an `[entity.item]` table, plus `consumable` or `equippable`.
- **Hostiles** are actors with `[entity.ai] hostile = true` and `stats`.

## 3. Read a load error

A broken pack fails before the game starts, with the file, the line, and the
reason:

```text
glyphwright: entities.toml:16: entity 'goblin-1': hp 9 is outside 0..6
```

Go to that line, fix that one thing, and load again. A key that a later
version will support says "is not supported by this engine version"; an
unknown key is a typo.

## 4. Playtest

Play the pack as described in the play-a-session skill, with `--harness`. Walk
through every portal, take every item, and meet every hostile. Check numbers
with `:query`, such as `:query goblin-1.hp`.

## 5. Check yourself

- Does the pack load with no error?
- Can the player reach every area, and every item and hostile you placed?
