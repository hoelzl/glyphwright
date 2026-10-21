# GlyphWright

A deterministic, turn-based RPG engine. You author worlds as data, and both
people and coding agents can play them.

> **No engine yet.** This repository starts with its structure, gates, and
> plans. The engine is ported from
> [GlyphWright v0](https://github.com/hoelzl/glyphwright-v0) slice by slice,
> and the first slice brings a playable area. What gets built, in which order,
> and why: the [project brief](docs/project-brief.md).

## Working on GlyphWright

Requirements: [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run python scripts/check.py
```

- **Contributors:** [`CONTRIBUTING.md`](CONTRIBUTING.md)
- **Coding agents:** [`AGENTS.md`](AGENTS.md)
- **All documentation:** [`docs/README.md`](docs/README.md)

## License

Apache-2.0; see [`LICENSE`](LICENSE).
