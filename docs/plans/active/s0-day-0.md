# S0 — Day 0

The plan and record of slice S0: the repository skeleton, the gates, CI, and
the agent-facing documentation, before any engine code. Read it to continue
S0 or to see why day 0 looks the way it does.

## Contents

- [Goal](#goal)
- [Progress](#progress)
- [Setup log](#setup-log)
- [Decisions](#decisions)
- [Surprises](#surprises)
- [How day 0 meets the documentation rules](#how-day-0-meets-the-documentation-rules)

## Goal

A repository that people and agents can work in before it has any engine:
`uv sync` and one check command work on Linux, macOS, and Windows, and the
documentation passes its own rules. S0 ends with an owner review; no engine
code is ported before it.

## Progress

- [x] uv project: package skeleton, Python 3.12–3.14, `[tool.uv]` table
- [x] `scripts/check.py`: one command for every gate
- [x] `scripts/docs_tool.py`: documentation rules, generated indexes, Claude
  Code stub generator, with tests
- [x] `AGENTS.md`, `README.md`, `CONTRIBUTING.md`, the documentation map
- [x] The project brief, moved here from the course repository
- [x] Decision 0001: the agent harness layout
- [x] CI on three operating systems and three Python versions
- [ ] Owner review of the S0 pull request
- [ ] Tag `day-0`; move this plan to `docs/plans/completed/`

## Setup log

**Added, because day 0 needs it:**

- One instruction file, `AGENTS.md`, as a map: the check command, the five
  invariants, how work is done, and where knowledge lives.
- One check command. It runs all gates even when one fails, so a single run
  shows every problem.
- Documentation gates with messages that name the rule and the fix.
- Two derived views, generated and checked: the docs indexes and the Claude
  Code command stubs.
- A decision record for the harness layout, because it rejects files that
  other repositories would add by habit.

**Deliberately not added yet:**

- **No engine code**, no CLI, no `glyphwright.api`: S1 ports them from v0.
- **No skills and no `.agents/skills/` folder.** A procedure becomes a skill
  after it has been done twice; nothing has been done twice yet. The stub
  generator is in place and tested, so the first skill gets its Claude Code
  stub with no further work.
- **No `docs/knowledge/`.** Each knowledge page arrives with the slice that
  ports its subsystem.
- **No `.claude/settings.json`, no pre-commit hooks, no Dependabot, no
  changelog.** Nothing needs them yet; light governance until an outside user
  depends on the project.
- **No folder-tree overview in `AGENTS.md`.** Agents can list the files, and
  overviews did not help agents in a controlled study.

## Decisions

- **Indexes are generated blocks inside each folder's `README.md`.** A page is
  listed in the nearest `README.md` above it, so `docs/plans/README.md` lists
  the plans in `active/` and `completed/` without an index per subfolder.
- **A page's purpose is the first paragraph under its title**, not
  frontmatter. Humans see it, indexes show it, and the docs tool needs no YAML
  library.
- **Paths named before they exist** are allowed only through `PLANNED` in
  `scripts/docs_tool.py`, each with its reason; the gate fails once a planned
  path exists, so the list cannot go stale.
- **`AGENTS.md` budget: 100 lines.**
- **Version `0.1.0.dev0`**, read from the package metadata. v0 never changed
  its version (finding H2); S5 makes the version part of replay checks.
- **`.gitattributes` forces LF line endings**, so generated files compare
  equal on Windows checkouts with `core.autocrlf`.

## Surprises

- The course's rule list lives in a private repository, so this repository
  cannot link it. The rules this repository follows are written out in
  `CONTRIBUTING.md`, and the gates enforce them by name.
- That an `@` import inside a Claude Code command file expands is observed
  behavior, not documented behavior. Decision 0001 records it as such.
- Several Copilot chat surfaces still read only
  `.github/copilot-instructions.md`. Decision 0001 records the trade-off of
  not shipping that file.

## How day 0 meets the documentation rules

| Rule | How day 0 meets it | Check |
|---|---|---|
| One instruction file | Only `AGENTS.md`; the others are rejected | gate |
| A map, not a manual | Routes, invariants, the check command; no tree tour | review |
| A size budget, enforced | 100 lines | gate |
| Pruning test | Every line routes, constrains, or names a command | review |
| Rules follow mistakes | Day 0 holds the initial set: the invariants and the lessons of v0 and termverify | review |
| "Always"/"never" become gates | The harness rule is a gate; the invariants get theirs in the slices that port the code | review |
| No volatile facts in prose | Versions and gate lists live in `pyproject.toml` and `scripts/check.py` | review |
| An index per docs folder | Generated blocks in each `README.md` | gate |
| References one level deep | Every page is one link from `AGENTS.md` or the map | review |
| A table of contents in long files | Over 100 lines | gate |
| Names say what is inside | `project-brief.md`, `0001-agent-harness-layout.md` | review |
| Every doc opens with its purpose | First paragraph under the title | gate |
| Skills valid to the specification | Checked once the first skill exists | gate |
| Descriptions say what and when | Applies to the first skill | review |
| `SKILL.md` under 500 lines | Checked once the first skill exists | gate |
| Generated stubs only where needed | Claude Code stubs, generated and checked | gate |
| One canonical home per fact | The brief links the invariants, working rules, and harness layout | review |
| Derived files say so | Index blocks and stubs carry a generated header | gate |
| Code wins over prose | Stated in `CONTRIBUTING.md` | review |
| Plans are files | This plan, in `active/` | gate |
| Decisions get a record | Decision 0001 | review |
| One check command with fix-it errors | `scripts/check.py`; docs messages name rule and fix | gate |
| Concise tool output | One line per problem, plus rule and fix | review |
