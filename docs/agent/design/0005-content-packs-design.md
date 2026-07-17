# TOML Content Packs — Design Document

| | |
|---|---|
| **Status** | Accepted — subordinate to `0003` |
| **Date** | 2026-07-17 |
| **Scope** | Scopes `0003` §8.2 into an implementable slice (slice 8) |
| **Authority** | `0003` wins on any disagreement; this document only refines it |

`0003` §8.2 settles the contract: a content pack is a directory of TOML files,
validated at load with hard errors and useful diagnostics, hashing to a pack id
in the run fingerprint. This document fixes the file layout and the diagnostic
depth.

## 1. Directory layout

```
<pack>/
  pack.toml            # manifest: name, and nothing else yet
  areas.toml           # [[grid]] and [[rooms]] area tables
  entities.toml        # [[entity]] tables, components as sub-tables
  abilities.toml       # [[ability]] and [[status]] tables (optional file)
```

Four files, not a tree: at reference-pack scale a directory-per-kind would be
empty ceremony, and a single file per concern keeps diagnostics short
(`entities.toml: entity 'goblin-1': …`). Growing into split files later is a
loader change, not a format change.

## 2. Mapping to engine types

The loader maps tables one-to-one onto the constructors that already validate
everything (`ContentPack.__post_init__`, `RoomGraphSpace`, `Dialogue`,
`StatModifier`, `Ability` param specs…). The loader adds no second validation
layer; it adds *location* to the errors the constructors already raise.

- `[[grid]]`: `area`, `rows` (multiline string).
- `[[rooms]]`: `area`, plus `[[rooms.room]]` with `id`, `name`, `description`,
  and an `exits` table of `token = destination`.
- `[[entity]]`: `id` plus optional component sub-tables mirroring the
  dataclasses (`actor`, `renderable`, `ai`, `portal`, `item`, `consumable`,
  `equippable`, `openable`, `dialogue`, `blocker = true`). Positions are
  `"area:local"` strings — the identifier syntax every event and query
  already speaks (`0003` §7.5).
- `[[ability]]` / `[[status]]`: fields mirroring `Ability`/`Status`, with
  `effects` as an array of `{ primitive = "...", ... params }` tables and
  modifiers as `{ stat, op, value }` tables.

## 3. Diagnostics

Three layers, each naming its location:

1. **TOML syntax**: `tomllib` errors carry line and column; the loader
   prefixes the file name (`areas.toml:12:3: …`).
2. **Shape**: missing/unknown keys and wrong types are reported as
   `<file>: <table> '<id>': <problem>` before any constructor runs.
3. **Semantics**: constructor `ValueError`s (dangling references, unreachable
   farewells, param specs) are re-raised with the same file/table prefix.

Line numbers for layers 2–3 would require a lossy re-parse; file plus table
id plus key path is the contract (`0003` §8.2 asks for "file/line
diagnostics" — syntax errors carry lines, semantic errors carry the sharper
thing: the exact content object).

## 4. The reference pack moves to TOML

`reference_pack()` now loads the packaged files under
`glyphwright/content/packs/reference-vale/` via `importlib.resources` — one
source of truth, and the loader is exercised by every existing test in the
suite. The Python-built pack is deleted, not kept as a shadow.

## 5. CLI

`glyphwright --pack <directory>` plays an external pack; the default remains
the packaged reference pack. The pack id in the session header already
invalidates baselines across content changes (`0003` §8.2).

## 6. Non-goals

Encounter tables, species/classes, TOML schema *export* (the published JSON
schemas cover the wire, not authoring), and hot reloading. `tomllib` is
stdlib: the zero-dependency stance holds.
