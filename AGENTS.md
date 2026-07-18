# GlyphWright — Agent Guide

GlyphWright is a deterministic, turn-based RPG engine. Its current vertical slice models a tile world, applies movement commands through a pure transition boundary, renders stable text snapshots, and exposes a terminal session that agents and people can drive.

This file is the authoritative guide for every agent tool used on this repository. Tool-specific entry points (`CLAUDE.md`) are pointers to it and carry no rules of their own.

## Start Here

1. Read `README.md` for current product behavior and quick start.
2. Read `docs/agent/design/0003-glyphwright-design.md` — the authoritative design document — before any non-trivial change.
3. Read `docs/knowledge/index.md`, then only the linked concept pages relevant to the task.
4. Read `docs/developer-guide/testing.md` before changing verification or terminal behavior.
5. Prefer executable code and checks over prose when they disagree; update stale docs in the same change.

Precedence: `0003` is the specification and overrides every other document here. If another document contradicts it, that document is the defect. Code that contradicts it is likewise the defect, not evidence of a decision — none of the current code was written against a detailed specification, so do not treat an existing shape as precedent or infer intent from it. Fix or replace it.

## Commands and Sources of Truth

| Task or fact | Command or authoritative source |
| --- | --- |
| Setup | `uv --no-config sync --all-groups --all-extras --locked` — `--all-extras` installs the optional `gui` extra (`pygame-ce`). Without it the GUI e2e tests **silently skip** (`tests/test_gui_e2e.py` opens with `pytest.importorskip("pygame")`) and the suite still reports green |
| Focused test | `uv --no-config run pytest tests/test_engine.py -q` |
| Full tests | `uv --no-config run pytest --cov --cov-report=term-missing` — set `SDL_VIDEODRIVER=dummy` for headless GUI runs, as CI does |
| Bare-suite check | `uv --no-config sync --all-groups --locked` (no `--all-extras`, which removes `pygame`), then `uv --no-config run pytest -q`, then re-sync with `--all-extras` to restore the GUI env. Proves the core suite passes with `pygame` absent; CI runs it as the separate `bare` job (`.github/workflows/ci.yml`). A stray top-level `pygame` import passes a normal local run and breaks this |
| Run the GUI | `uv --no-config run glyphwright --frontend gui` (add `--tiles` for the reference pack's tileset); requires the `gui` extra |
| Lint | `uv --no-config run ruff check .` |
| Format check | `uv --no-config run ruff format --check .` |
| Type check | `uv --no-config run mypy --platform win32 src tests`, then again with `--platform linux` — mypy's verdict is platform-dependent (`sys.platform` narrowing), and CI checks both |
| Full local gate | `uv --no-config run pre-commit run --all-files` then `uv --no-config run pre-commit run --hook-stage pre-push --all-files` |
| Dependencies and Python support | `pyproject.toml` and `uv.lock` |
| CLI contract | `glyphwright --help`, `src/glyphwright/cli.py`, and e2e tests |
| Current work state | GitHub issues/PRs and `git status` |

## Layout and Invariants

- `src/glyphwright/`: package; core engine modules must not perform terminal, clock, filesystem, or network I/O, and must not read ambient entropy.
- `tests/`: unit/property tests plus marked terminal-facing e2e tests.
- `docs/developer-guide/`: stable contributor workflows.
- `docs/knowledge/`: OKF knowledge bundle for product, architecture, terms, and verification.
- `docs/agent/design/`: the authoritative design document, decisions, roadmap, and reuse assessments.

The transition shape is `step(state, command, rng) -> (next_state, ordered_events)`, with invalid commands producing a typed rejection rather than an exception, and the successor state being the fold of events over the prior state (`0003` §5).

State and returned event collections are immutable. Coordinates, command parsing, rendering order, and event order are deterministic. Randomness is not banned — it is injected as a seeded stream whose cursor lives in world state; ambient entropy is what is banned. Time is the turn counter; there is no wall clock in the kernel. Terminal text is an interaction surface and evidence source, not the sole semantic oracle. Clock, persistence, content loading, and network services must enter through an explicit boundary. GlyphWright must never import `termverify` (`0003` ADR-001).

## Documentation Placement

| Document kind | Location |
| --- | --- |
| Human introduction and quick start | `README.md` |
| Contributor workflow | `CONTRIBUTING.md` and `docs/developer-guide/` |
| Durable product, architecture, terminology, verification | `docs/knowledge/` |
| Authoritative design, decisions, reuse assessments, roadmap | `docs/agent/design/` |
| Slice and work status | `docs/agent/design/roadmap.md` — **the single authoritative source.** Never record slice status in a second file |
| Active multi-session implementation state | `docs/agent/handovers/` only when needed, and only for work genuinely in flight. Retire to `docs/agent/handovers/archive/` when it completes; a retired handover carries a non-authoritative banner |

Every non-index Markdown file in `docs/knowledge/` has OKF frontmatter with at least `type`. Do not create empty documentation taxonomies.

## Multi-Agent Contract

More than one agent tool works on this repository, and no tool can read another's local state. Durable knowledge therefore lives in tracked files, never in an agent's private memory.

- Record project facts, conventions, decisions, and work state in the repository, using the Documentation Placement table above. A note that exists only in one agent's memory is invisible to every other agent and to human contributors.
- Keep rules in this file. When guidance changes, edit `AGENTS.md`; do not let a tool-specific file accumulate its own copy.
- Agent-local memory is acceptable only for facts about the individual operator or their machine, never for facts about GlyphWright.

| Agent tooling file | Purpose |
| --- | --- |
| `AGENTS.md` | Authoritative agent guide; read by hermes and by any tool that supports the convention. |
| `CLAUDE.md` | Pointer for Claude Code, which loads `CLAUDE.md` instead of `AGENTS.md`. |
| `.claude/settings.json` | Tracked Claude Code permissions for the commands above. Claude-Code-specific: another harness needs its own allowlist for the same commands, and nothing here is authoritative for it. |
| `.claude/settings.local.json` | Per-developer overrides; untracked by design. |

Where a workflow step names a tool-specific command, it is describing intent, not a
requirement. "Run an adversarial review before merging" means: have a reviewer that did
not write the change look for correctness bugs, contract violations, and missed test
cases, and record what it found. A harness without a review command should substitute
its own equivalent rather than skip the step.

## Completion Contract

Use strict TDD for behavior changes: watch a focused test fail for the intended reason, implement the minimum, then run wider checks. Test semantic behavior separately from terminal wiring. Do not add dependencies, copy code, bless baselines, or change replay/protocol contracts without a written rationale and review plan. Before completion, run relevant tests, lint, format, mypy, and build/package checks. If the change touches the GUI or any optional-extra boundary, run the bare-suite check too — a green normal run does not cover it.

### Documentation checklist

"Update docs when behavior changes" is too vague to check, and has been satisfied while leaving real drift behind. Before completion, walk this list explicitly:

| If the change… | Update |
| --- | --- |
| completed or altered a slice's status | `docs/agent/design/roadmap.md` — the **single** authoritative status source. Do not record slice status anywhere else; a second copy will drift |
| made a design decision | `docs/agent/design/` (the relevant numbered document). A decision recorded **only in a commit message is lost** — commit messages are not in the Documentation Placement table |
| changed CLI surface, setup, or test commands | `README.md` **and** the commands table above |
| resolved or reopened an open question | the owning design document's open-questions section |
| changed rules for agents | this file, `AGENTS.md` |

If none apply, say so rather than skipping the list silently.
