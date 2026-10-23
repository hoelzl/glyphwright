# Documentation map

Every document in this repository, with what it covers and when to read it.
Start here when `AGENTS.md` does not route you to a page directly.

- **Coding agents** start with [`AGENTS.md`](../AGENTS.md).
- **Contributors** start with [`CONTRIBUTING.md`](../CONTRIBUTING.md).
- **Content authors** start with [`authoring/`](authoring/README.md).

<!-- BEGIN GENERATED INDEX: edit the listed pages, not this list; regenerate with `uv run python scripts/docs_tool.py build` -->
- [authoring/: Authoring content](authoring/README.md): Guides for people and agents who write content packs: start with the first-pack walkthrough, then use the format reference while you write.
- [decisions/: Decision records](decisions/README.md): Short records of decisions that shape the repository or the engine: the context, the decision, and its consequences. Read the one that covers what you are about to change. What a record decided is never rewritten; a later record supersedes it. A slip that leaves the decision as it was is fixed in place, with a dated entry that quotes the old text.
- [knowledge/: Knowledge](knowledge/README.md): One page per subsystem or contract, each added by the slice that ports it. Read the page for the part of the engine you are about to change.
- [plans/: Plans](plans/README.md): One plan per slice of work. A plan lives in `active/` while its work runs and moves to `completed/` when the work is done, so the folder says whether a plan is current. Read the active plan before you continue its work.
- [GlyphWright v2 — Project brief](project-brief.md): What GlyphWright v2 is, who it serves, what the core must do, and the slices that build it. Read it before you plan or start a slice.
<!-- END GENERATED INDEX -->
