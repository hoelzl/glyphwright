# 0001 — One instruction file and one skills folder for all agent harnesses

Which files give coding agents their instructions and skills, why there is
exactly one of each, and what that costs. Read it before you add, move, or
rename any agent-facing file.

- **Date:** 2026-10-21
- **Status:** accepted

## Context

Contributors use different coding agents. Copilot and Claude Code must work;
Codex, OpenCode, and Hermes Agent should, if that costs almost nothing.
Copying instructions or skills into each tool's own location is the usual way
to support several tools, and the copies drift apart.

What each tool read, checked against its documentation on 2026-10-21:

| Harness | Reads `AGENTS.md` | Reads `.agents/skills/` |
|---|---|---|
| Claude Code | Yes, but only while no `CLAUDE.md`, `.claude/CLAUDE.md`, or `CLAUDE.local.md` exists at or above the working directory ([memory docs](https://code.claude.com/docs/en/memory)) | No; it reads `.claude/skills/` and `.claude/commands/` ([skills docs](https://code.claude.com/docs/en/skills)) |
| Copilot | Agent mode, cloud agent, CLI, and code review on GitHub.com; several chat surfaces read only `.github/copilot-instructions.md` ([support table](https://docs.github.com/en/copilot/reference/custom-instructions-support)) | Yes, and also `.claude/skills/` and `.github/skills/` |
| Codex | Yes, from the repository root down to the working directory ([docs](https://learn.chatgpt.com/docs/agent-configuration/agents-md)) | Yes ([docs](https://learn.chatgpt.com/docs/build-skills)) |
| OpenCode | Yes; `CLAUDE.md` only when no `AGENTS.md` exists ([docs](https://opencode.ai/docs/rules/)) | Yes, and also `.claude/skills/` ([docs](https://opencode.ai/docs/skills/)) |
| Hermes Agent | Yes ([docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/context-files)) | Yes, after `hermes skills trust` ([docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills)) |

## Decision

- **`AGENTS.md` is the only instruction file.** There is no `CLAUDE.md`: its
  presence would stop Claude Code from reading `AGENTS.md`. If a Claude Code
  version or session does not load `AGENTS.md`, the fallback is a `CLAUDE.md`
  whose only line is `@AGENTS.md`.
- **No `.github/copilot-instructions.md`.** The Copilot chat surfaces that read
  only that file get no project instructions. Copilot's agents, which do the
  work in this repository, read `AGENTS.md`. A second file would have to stay
  a pointer forever, and on those surfaces a pointer is all it could be.
- **`.agents/skills/` is the only skills folder.** Copilot and OpenCode read
  `.claude/skills/` as well, so a copy there would list every skill twice.
- **Claude Code gets one generated stub per skill** in `.claude/commands/`.
  The stub copies the skill's `description` into its frontmatter, imports
  `@.agents/skills/<name>/SKILL.md`, and forwards `$ARGUMENTS`.
  `scripts/docs_tool.py build` writes the stubs; `check` fails when one is
  stale.
- **Claude-only settings and hooks** go into `.claude/settings.json`, once
  there is something to put there.

## Consequences

- `scripts/docs_tool.py check` rejects a `CLAUDE.md` other than the fallback,
  `CLAUDE.local.md`, `.claude/CLAUDE.md`, `.github/copilot-instructions.md`,
  `.claude/skills/`, and `.github/skills/`.
- The stub mechanism rests on behavior that was verified, not documented.
  Claude Code's documentation says command files keep working and accept the
  skill frontmatter. That an `@` import inside a command file expands, and
  that Claude invokes such a stub on its own, was observed in another
  repository on 2026-10-20. Re-test it when Claude Code changes how it loads
  commands.
- These locations change between tool versions. Re-check the table before a
  change to the layout, and record a change as a new decision.
