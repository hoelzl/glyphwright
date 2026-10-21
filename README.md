# GlyphWright

A deterministic, turn-based RPG engine. You author worlds as data, and both
people and coding agents can play them.

> **Early days.** The engine is ported from
> [GlyphWright v0](https://github.com/hoelzl/glyphwright-v0) slice by slice.
> So far you can walk around one small village. What gets built, in which
> order, and why: the [project brief](docs/project-brief.md).

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run glyphwright
```

Type `move east`, `move south`, `look`, or `wait`; `help` lists what is valid
right now, and `quit` ends the session. Every turn prints a block that opens
with `== turn N | mode | area ==`.

For agents and scripts, `uv run glyphwright --frontend jsonl` speaks one JSON
object per line: a session header, then a frame after every command, with the
events before it. Add `--harness` for the meta commands `:seed` and `:frame`.
The JSON shapes are in `schemas/`.

## Working on GlyphWright

```bash
uv sync
uv run python scripts/check.py
```

- **Contributors:** [`CONTRIBUTING.md`](CONTRIBUTING.md)
- **Coding agents:** [`AGENTS.md`](AGENTS.md)
- **All documentation:** [`docs/README.md`](docs/README.md)

## License

Apache-2.0; see [`LICENSE`](LICENSE).
