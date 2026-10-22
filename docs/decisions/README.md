# Decision records

Short records of decisions that shape the repository or the engine: the
context, the decision, and its consequences. Read the one that covers what you
are about to change. Records are numbered and never rewritten; a later record
supersedes an earlier one.

<!-- BEGIN GENERATED INDEX: edit the listed pages, not this list; regenerate with `uv run python scripts/docs_tool.py build` -->
- [0001 — One instruction file and one skills folder for all agent harnesses](0001-agent-harness-layout.md): Which files give coding agents their instructions and skills, why there is exactly one of each, and what that costs. Read it before you add, move, or rename any agent-facing file.
- [0002 — Wire schema tags restart at version 1](0002-wire-schema-versions.md): How the JSON wire contract is versioned, and why v2's tags do not continue v0's numbers. Read it before you change an encoder in `src/glyphwright/frontends/wire.py` or a schema under `schemas/`.
- [0003 — A rules revision, pinned by a recording](0003-rules-revision.md): How a recording names the behaviour that produced it, and what forces that name to change. Read it before you change anything that alters what the same commands produce, or when the pinned recording fails.
<!-- END GENERATED INDEX -->
