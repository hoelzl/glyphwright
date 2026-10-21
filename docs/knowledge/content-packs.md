# Content packs

How a pack becomes a validated `ContentPack`: the three files, the loader's
layers of checks, how diagnostics find their line, the I/O boundary, and pack
identity, plus the checklist for adding a key or a component to the format.
Read it before you change `src/glyphwright/content/` or add an entity
component. Authors writing a pack want [`docs/authoring/`](../authoring/README.md)
instead.

## Contents

- [The pipeline](#the-pipeline)
- [Three layers of checks](#three-layers-of-checks)
- [How a diagnostic finds its line](#how-a-diagnostic-finds-its-line)
- [The I/O boundary](#the-io-boundary)
- [Pack identity](#pack-identity)
- [Adding a key or a component](#adding-a-key-or-a-component)

## The pipeline

1. `api.load_pack(root)` reads every `*.toml` file in the directory.
2. `parse_pack(sources)` in `src/glyphwright/content/loader.py` parses each
   file's text and checks its shape.
3. It builds `GridSpace`s and `Entity`s and hands them to `ContentPack`, whose
   constructor checks the content rules.
4. Every problem becomes one `PackError` with a file, a line where known, and
   a message. Loading stops at the first problem.

The reference world, `src/glyphwright/content/packs/reference-vale/`, loads
through the same path, so the whole test suite exercises the loader.

## Three layers of checks

| Layer | Where | Examples |
|---|---|---|
| Syntax | `tomllib` | an unclosed string, `hp = = 20` |
| Shape | the loader's specs | an unknown key, a missing key, `hp = "20"` |
| Content | `ContentPack` | a duplicate id, a wall under an entity, a portal shadowing an exit |

Keys and files of later slices (`openable`, `abilities.toml`, …) live in
the loader's `_LATER_*` sets and fail with "is not supported by this engine
version", so a typo and a missing feature read differently. Every content
rule raises `ContentError`, whose `subject` names the area or entity it is
about.

## How a diagnostic finds its line

`tomllib` reports a line and column only for syntax errors. For shape and
content errors the loader indexes the `[[grid]]` and `[[entity]]` headers in
the source with `header_lines`, which skips strings and comments, so grid
rows inside multi-line strings cannot look like headers. The k-th header
defines the k-th table, so an error about that table is reported at its
header line. A content error is mapped back through its `subject`; a
duplicate id is reported at its second definition.

When the number of headers and the number of tables disagree, as with an
inline array of tables, the line is left out rather than guessed.

## The I/O boundary

`content` belongs to the core, which does no I/O. The loader therefore takes
text, and `api.load_pack` does the reading. `tests/test_invariants.py`
enforces this: the core may not import `importlib`, `pathlib`, or other I/O
modules.

## Pack identity

`ContentPack.pack_id` is `name@sha256:<digest>` over every field of every area
and entity, so any content change changes the id, and the run fingerprint
records it. Adding a component to `Entity` changes every pack's id; re-pin
`test_the_pack_identity_derivation_is_pinned` in `tests/test_determinism.py`
in the same change and say so in the slice plan's setup log.

## Adding a key or a component

1. Add the field or component to `src/glyphwright/world/entities.py` with a
   default, so existing content keeps loading.
2. Move its key from the loader's `_LATER_*` set into the matching spec, and
   build it in `_entity` or `_areas`.
3. Add its content rules to `ContentPack`, raising `ContentError` with the
   entity or area as subject.
4. Document the key in
   [`docs/authoring/pack-format.md`](../authoring/pack-format.md); a test fails
   until every accepted key appears there, above "Not supported yet".
5. Re-pin the pack-id test if `Entity` gained a component.
