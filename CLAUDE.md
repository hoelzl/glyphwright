# CLAUDE.md

The agent guide for this repository is [`AGENTS.md`](AGENTS.md). **Read it now** — it is
the single source of truth for start-here reading order, commands, layout, invariants,
documentation placement, and the completion contract.

This file exists only because Claude Code loads `CLAUDE.md` rather than `AGENTS.md`. It
intentionally contains no project rules of its own: any guidance duplicated here would
drift out of sync with `AGENTS.md` and silently give different agents different rules.

## Working alongside other agents

This repository is worked on by more than one agent tool. Durable knowledge therefore
belongs in tracked files, never in agent-local memory:

- Anything a future session must know goes in the repository, in the location given by
  the Documentation Placement table in `AGENTS.md`.
- Do not record project facts, conventions, or work state in Claude Code's own memory
  directory. It is invisible to every other agent and to human contributors.
- Active multi-session implementation state goes in `docs/agent/handovers/`.
- When rules change, edit `AGENTS.md` — not this file.
