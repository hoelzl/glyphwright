# Project contract

Status: accepted 2026-07-17; revised to agree with `0003-glyphwright-design.md`, which is
authoritative for GlyphWright's purpose, scope, and design. This document records only the
facts `0003` does not: identity, ownership, licensing, toolchain, and the agent boundary. It
does not define product scope — `0003` §2 and §18 do.

## Identity and users

- Repository/package: `glyphwright` / GlyphWright.
- Purpose: a deterministic, terminal-first turn-based RPG engine, and a reference application under test for [TermVerify](https://github.com/hoelzl/termverify).
- Intended users: game authors and engine developers building turn-based RPGs, plus autonomous agents that must play, inspect, test, and extend GlyphWright games cheaply.

## Ownership, publication, and license

- Local destination: `C:\Users\tc\Programming\Python\Projects\glyphwright`.
- Remote: `hoelzl/glyphwright` on GitHub. GlyphWright is its own repository, not a workspace member under TermVerify (`0003` §20.4, resolved).
- License: Apache-2.0, matching TermVerify and permitting future documented reuse. Copyright: Matthias Hölzl, 2026.

## Runtime and verification

Use `uv`, a `src/` package, and Python 3.12 minimum. CI tests 3.12–3.14 on Windows and Linux. Fast local checks are Ruff lint/format; wider checks are pytest with coverage reporting, strict mypy, pre-commit/pre-push hooks, package build, and wheel/sdist import smoke tests. Coverage is reported without an initial threshold. The core test suite must remain runnable without TermVerify installed (`0003` §16.1).

## Agent boundary

Agents may run the CLI, tests, formatters, type checker, build, and deterministic subprocess sessions. `0003` is authoritative for game rules and design; tests and versioned contracts are authoritative for observable behavior. Agents may change local code and docs within a scoped task, but may not push to the public remote, add dependencies, copy donor code, alter protocol commitments, or approve baselines without explicit review.

Existing code carries no authority. The initial repository contents were generated during bootstrap without a detailed specification; where they diverge from `0003`, `0003` wins and the code is replaced. Do not infer design intent from code shape, and do not preserve an existing structure merely because it is there.
