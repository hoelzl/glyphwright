# S2 — Content packs

The plan and record of slice S2: TOML content packs with located diagnostics,
portals between grid areas, and a two-area reference world loaded from a
packaged pack. Read it to continue S2 or to see what was cut from v0 and why.

## Contents

- [Goal](#goal)
- [Scope](#scope)
- [Defects fixed in the port](#defects-fixed-in-the-port)
- [Progress](#progress)
- [Setup log](#setup-log)
- [Decisions](#decisions)
- [Surprises](#surprises)

## Goal

An author writes a pack as three TOML files and plays it with
`glyphwright --pack <dir>`. A broken pack fails at load with a diagnostic that
names the file, the line, and the problem. The built-in reference world is
itself a pack, with two areas joined by portals.

## Scope

Ported from
[v0 at `3ecc396`](https://github.com/hoelzl/glyphwright-v0/tree/3ecc396).

| Area | S2 keeps | Later |
|---|---|---|
| Format | `pack.toml` (`name`); `areas.toml` (`[[grid]]`); `entities.toml` (`[[entity]]` with position, actor, blocker, renderable, portal) | items, stats (S3); AI (S4); rooms, dialogue, abilities, presentation (deferred) |
| Diagnostics | `file:line:col` for syntax errors; `file:line` for shape and content errors, from an index of table headers | none |
| World | `Portal` component; portals join `WorldState.exits_from` | room-graph geometry (deferred) |
| Reference world | `village` and `warren`, linked by a portal pair, with inert actors | items and the inn (later slices) |
| I/O | files are read by `api.load_pack`; the loader parses text | none |

Keys from later slices fail with "not supported by this engine version", so a
v0-era pack fails loudly instead of silently playing differently.

## Defects fixed in the port

| ID | Defect | Fix |
|---|---|---|
| K10 | a portal token can shadow a geometric exit | refuse it at load; refuse portals on actors and on blockers |
| L1, L2 | duplicate ids, hp out of range | already refused; now located in the TOML |
| N1 | positions like `village: 1,1` load but match no tile | require the canonical `area:x,y` form |
| N2 | an area name with whitespace or `:` breaks position parsing | refuse it |
| N3 | one glyph with two labels loses a legend entry | refuse it |
| N4 | entities may stand on walls, and portals may lead into them | require floor |
| N5 | two blockers may share a tile | refuse it |
| N6 | a UTF-8 byte-order mark breaks the TOML parser | decode with `utf-8-sig` |

N1 to N6 were found while planning S2; they are not in v0's register.

## Progress

- [x] Plan; brief updated for portals
- [x] `Portal`, the `exits_from` merge, portal checks (K10), and N1 to N5
- [x] Pure loader with located `PackError` and the header index (N6)
- [x] `api.load_pack` and `api.reference_pack`; the I/O boundary
- [x] Two-area reference world; goldens
- [x] CLI `--pack`
- [x] Content-pack knowledge page; kernel page on portals
- [x] Authoring docs (first pack, pack format); docs map; README; `AGENTS.md`
- [x] Owner review of the S2 pull request (merged as #3)
- [x] Tag `s2`; move this plan to `docs/plans/completed/`

## Setup log

**Added, because S2's content needs it:**

- `docs/authoring/`, the content authors' entry point: the brief names three
  audiences, and this is the second one's path. It holds a walkthrough and
  the format reference.
- `docs/knowledge/content-packs.md`, for engine developers who change the
  loader, ending with the checklist for adding a key.
- Two `AGENTS.md` routes, one per audience, and a pointer for authors in the
  docs map and the README.
- A test that keeps the hand-written format reference complete against the
  loader's specs.

**Deliberately not added yet:**

- **No `author-a-pack` skill.** Writing a pack has been done once, in this
  port. The skill comes after the second real run, at the latest before the
  usability gate in S5.
- **No generated format reference.** The hand-written page plus its test is
  enough for six small tables.

## Decisions

- **Portals come with S2** (owner, 2026-10-21), because the usability gate
  needs a two-area pack. Rooms stay deferred.
- **Unknown keys are located errors.** Keys of later slices get their own
  message, so a typo and a missing feature read differently.
- **Line numbers come from an index of table headers.** `tomllib` reports
  positions only for syntax errors. The k-th `[[entity]]` header is exactly
  the k-th entity, so a shape or content error is reported at its header; when
  the scan and the data disagree, the line is left out rather than guessed.
- **Reading files moves to the API.** `content` is part of the core, which does
  no I/O, so the loader parses text and `api.load_pack` reads the files.
- **The pack-format reference is hand-written, with a test** that every key the
  loader accepts appears in it. A generator would add machinery this slice
  does not need.

## Surprises

- **`tomllib` has no positions** except for syntax errors, and v0's design
  promised `file:line:col` diagnostics its code never produced. The header
  index gives every shape and content error a line.
- **A frozen dataclass cannot be an exception:** raising sets
  `__traceback__`, which a frozen dataclass refuses. `PackError` became a
  plain exception class before any test ran into it.
- **A commit went in with a lint failure.** The check's output was piped
  through `tail`, which hid its exit status from the `&&` that guarded the
  commit. It was amended before the push, and commits are now gated on the
  check's own exit status. One occurrence, so not yet a rule.
- **The format-reference test caught a gap on its first run:** the page named
  the `actor`, `renderable`, and `portal` tables only by their TOML headers.
- **The wheel ships the pack files** with no build configuration.

