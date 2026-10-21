# GlyphWright — Agent Guide

The always-on map for coding agents: the check command, the hard invariants,
how work is done here, and where each kind of knowledge lives. Read the linked
page for a task before you start it; the documentation map is
[`docs/README.md`](docs/README.md).

## Check

`uv run python scripts/check.py` runs every gate: lint, format, documentation
rules, types, and tests. Run it before you report a change as done. Each
documentation failure names the rule and the fix.

`uv run python scripts/docs_tool.py build` regenerates the derived views (the
docs indexes and the Claude Code command stubs). Never edit them by hand.

## Invariants

These hold for all engine code. Each one gets its enforcing test or lint rule
in the slice that ports the code it governs.

- **Determinism is a contract.** A run is fully determined by engine version,
  content-pack hash, seed, and command sequence.
- **No ambient I/O in the core.** Core modules do no terminal, clock,
  filesystem, or network I/O and read no ambient entropy. Turn count is time.
- **Invalid input is a value.** Invalid commands produce typed rejections,
  never exceptions.
- **Semantic evidence first.** Frames and events are the observations; text is
  a projection of them.
- **One public surface.** `glyphwright.api` is the only public programmatic
  surface.

## How work is done

- **Slices.** Work proceeds in the slices of the project brief. Each slice has
  a plan in `docs/plans/active/`; keep its progress, surprises, and decisions
  current as you work.
- **Port, don't rewrite.** Engine code comes from
  [v0 at commit `3ecc396`](https://github.com/hoelzl/glyphwright-v0/tree/3ecc396).
  Fix the v0 defects the brief lists inside the slice that ports the affected
  code, and record each fix in the slice plan.
- **Every slice adds something a user can do.** Hardening, frontends, or
  integrations that no observed use asked for wait.
- **Reviews are capped:** at most two rounds per change. A review opens an
  issue only for a blocker.
- **Rules follow mistakes.** Add a line here only after an agent got something
  wrong twice, and name the mistake in the PR.

## Where knowledge lives

| Task | Read first |
|---|---|
| Goals, scope, slices, working rules | [`docs/project-brief.md`](docs/project-brief.md) |
| The current slice | the plan in `docs/plans/active/` |
| Why the repository is laid out as it is | [`docs/decisions/`](docs/decisions/README.md) |
| Gates, commits, documentation rules | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| How v0 did it | [glyphwright-v0 at `3ecc396`](https://github.com/hoelzl/glyphwright-v0/tree/3ecc396) |

## Sources of truth

| Question | Ask |
|---|---|
| Dependencies, supported Python versions | `pyproject.toml`, `uv.lock` |
| Which gates run | `uv run python scripts/check.py --list` |
| Do the Claude Code stubs still load their skills? | `uv run python scripts/probe_claude_stubs.py` |
| Current work | the active plan, GitHub issues and PRs |

## Agent harnesses

`AGENTS.md` is the only instruction file and `.agents/skills/` the only skills
folder; Claude Code reaches each skill through a generated stub in
`.claude/commands/`. Never add a `CLAUDE.md`, a second skills folder, or
`.github/copilot-instructions.md`; the documentation gate rejects them. Why,
and the trade-off for Copilot chat surfaces:
[decision 0001](docs/decisions/0001-agent-harness-layout.md).
