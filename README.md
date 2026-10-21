# GlyphWright

A deterministic, turn-based RPG engine. You author worlds as data, and both
people and coding agents can play them.

> **Early days.** The engine is ported from
> [GlyphWright v0](https://github.com/hoelzl/glyphwright-v0) slice by slice.
> So far you can walk a small village and the warren beneath it, take, use,
> and equip items, and fight the hostiles you meet in menu battles, or play a
> world you write yourself. What gets built, in which order, and why: the
> [project brief](docs/project-brief.md).

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run glyphwright
```

Type `move east`, `take potion-minor`, `use potion-minor`, `look`, or `wait`;
step next to a hostile and a battle starts, where you `attack`, `use`, or
`flee`. `help` lists what is valid right now, and `quit` ends the session.
Every command is in the [command reference](docs/knowledge/commands.md).
Every turn prints a block that opens with `== turn N | mode | area ==`.

To play your own world, write a content pack and pass its directory with
`--pack`; [`docs/authoring/`](docs/authoring/README.md) shows how.

For agents and scripts, `uv run glyphwright --frontend jsonl` speaks one JSON
object per line: a session header, then a frame after every command, with the
events before it. Add `--harness` for the meta commands, such as
`:query player.stats.atk --explain`, which shows a stat and every
contribution to it. The JSON shapes are in `schemas/`.

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
