# Decision records

Short records of decisions that shape the repository or the engine: the
context, the decision, and its consequences. Read the one that covers what you
are about to change. What a record decided is never rewritten; a later record
supersedes it. A slip that leaves the decision as it was is fixed in place,
with a dated entry that quotes the old text.

<!-- BEGIN GENERATED INDEX: edit the listed pages, not this list; regenerate with `uv run python scripts/docs_tool.py build` -->
- [0001 — One instruction file and one skills folder for all agent harnesses](0001-agent-harness-layout.md): Which files give coding agents their instructions and skills, why there is exactly one of each, and what that costs. Read it before you add, move, or rename any agent-facing file.
- [0002 — Wire schema tags restart at version 1](0002-wire-schema-versions.md): How the JSON wire contract is versioned, and why v2's tags do not continue v0's numbers. Read it before you change an encoder in `src/glyphwright/frontends/wire.py` or a schema under `schemas/`.
- [0003 — A rules revision, pinned by a recording](0003-rules-revision.md): How a recording names the behaviour that produced it, and what forces that name to change. Read it before you change anything that alters what the same commands produce, or when the pinned recording fails.
<!-- END GENERATED INDEX -->

## Changing a record

- **A slip** (a wrong fact in the context, a misleading phrase, a broken
  link) that leaves the decision and its consequences as they were: fix it
  in the record and add an entry to its `## Revisions` section, the
  record's last. The entry opens with the date and the section it changed,
  quotes the replaced text, and says why:
  `- **2026-10-23**, Context: was "…". Why it was wrong.`
  Entries are never removed, so the record shows every earlier wording
  without git.
- **A change to what was decided or to its consequences:** write a new
  record that supersedes the old one. In the old one, set the status to
  "superseded by NNNN" and log that as a revision.

`docs/decisions/seals.json` records what each record said at its last
revision; `uv run python scripts/docs_tool.py build` updates it. The check
fails when a record changed without a new entry, when its Decision section
changed without an entry that names `Decision`, when an entry was removed,
and when a record was deleted. Name `Decision` only for a wording fix that
cannot change what any reader does.
