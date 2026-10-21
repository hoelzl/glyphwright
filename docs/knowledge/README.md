# Knowledge

One page per subsystem or contract, each added by the slice that ports it.
Read the page for the part of the engine you are about to change.

<!-- BEGIN GENERATED INDEX: edit the listed pages, not this list; regenerate with `uv run python scripts/docs_tool.py build` -->
- [Commands](commands.md): Every command, rejection, meta command, and query path the engine accepts, generated from the code that implements them. Read it when you play a session, drive the JSONL stream, or write a verifier.
- [Content packs](content-packs.md): How a pack becomes a validated `ContentPack`: the three files, the loader's layers of checks, how diagnostics find their line, the I/O boundary, and pack identity, plus the checklist for adding a key or a component to the format. Read it before you change `src/glyphwright/content/` or add an entity component. Authors writing a pack want [`docs/authoring/`](../authoring/README.md) instead.
- [The kernel](kernel.md): How a turn is computed: the world state, commands and events, the step function, modes, and rejections, plus the checklist for adding a command or an event. Read it before you change anything under `src/glyphwright/kernel/` or `src/glyphwright/modes/`.
<!-- END GENERATED INDEX -->
