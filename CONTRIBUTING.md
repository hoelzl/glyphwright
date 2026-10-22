# Contributing to GlyphWright

How to work on GlyphWright, for people and coding agents: setup, the gates,
commits and slices, the working rules, and the documentation rules the gates
enforce. Read it before your first change.

## Setup and gates

```bash
uv sync
uv run python scripts/check.py
```

`scripts/check.py` is the only list of gates; `--list` prints it. CI runs the
same script on Linux, macOS, and Windows for every supported Python version.

The repository stores every text file with LF line endings
(`.gitattributes`). On Windows, git may warn that "CRLF will be replaced by
LF" when a tool wrote CRLF; the warning is harmless, and the commit gets LF.

## Slices, commits, and tags

- Work proceeds in the slices of the [project brief](docs/project-brief.md).
  Each slice gets a plan in `docs/plans/active/` when it starts and moves to
  `docs/plans/completed/` when it is done. A change outside a slice needs no
  plan; its PR description records it.
- A plan is self-contained: a new session can continue from it alone. It keeps
  progress, surprises, and decisions current, plus a short setup log: what
  structure the slice added, what it deliberately did not add, and why.
- One concern per commit, with a message that says why. The history of
  `AGENTS.md` and of the documentation map should read as a story.
- Each finished slice gets a tag: `day-0`, then `s1` to `s5`. A snapshot the
  course teaches from gets a course tag, `course-1` and onward. Tags are
  never moved: a fix after a tag gets the next one.

## Working rules

These are the lessons of GlyphWright v0 and termverify.

- **Every slice must add something a user can do.** Hardening that no observed
  use asked for is deferred.
- **Reviews are capped.** At most two review rounds per change. A review
  creates a new issue only for something that blocks.
- **Light governance.** No release process, changelog fragments, or handover
  documents before an outside user depends on the project. Plans and decision
  records are enough.
- **No speculative frontends or integrations.** Growth past the core follows
  use, one feature at a time.
- **Check the ratio.** Now and then, check the share of merged PRs that added
  a capability.

## Documentation rules

`scripts/docs_tool.py check` enforces the rules marked *gate*; reviews check
the others. The IDs in brackets refer to the information-architecture rules
that the course using this repository distributes with its materials.

- **`AGENTS.md` is a map**: routes, invariants, the check command. It stays
  within its line budget (*gate*), and every line passes the pruning test:
  would removing it make an agent go wrong? [A2–A4]
- **One instruction file and one skills folder** (*gate*); see
  [decision 0001](docs/decisions/0001-agent-harness-layout.md). [A1, C1, C4]
- **Every doc opens with its purpose**: a `# Title`, then one plain paragraph
  that says what the page covers and when to read it (*gate*). Indexes show
  that paragraph. [B6]
- **Every docs folder has an index**: each page under `docs/` is listed in the
  nearest `README.md` above it, in a generated block (*gate*). [B1]
- **Long files start with a table of contents**: over 100 lines, the first
  `##` heading is `## Contents` (*gate*). [B4]
- **Every link and backticked repository path resolves** (*gate*). A path that
  is named before it exists goes into `PLANNED` in `scripts/docs_tool.py`,
  with its reason. [B3]
- **Derived views are never edited by hand** (*gate*): rerun
  `uv run python scripts/docs_tool.py build`. [D2]
- **Skills follow the [Agent Skills specification](https://agentskills.io/specification)**
  (*gate*), and a procedure becomes a skill only after it has been done twice.
  [C1–C3]
- **Plans live in `active/` or `completed/`** (*gate*). [E1] Default searches
  skip `completed/` (see `.ignore`), so finished plans do not answer questions
  about the current code; open them from the plans index. [E3]
- **One canonical home per fact.** Link to it instead of restating it, and
  prune the old wording in the same change. [D1]
- **No volatile facts in prose.** Versions, counts, and status live behind a
  command or a file that tools read. [A7] Versioned schema tags are refused
  (*gate*) outside decision records and plans.
- **When code and prose disagree, the code wins**; fix the prose in the same
  change. [D3]
- **Decisions get a short record** in `docs/decisions/`. [E2]
