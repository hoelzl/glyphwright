# S5 — Record and replay

The plan and record of slice S5: session recording and replay with exact
verdicts, the rules revision that makes engine identity mean something, the
determinism contract, the first skills, and the usability gate that ends the
core. Read it to continue S5 or to see what was cut from v0 and why.

## Contents

- [Goal](#goal)
- [Scope](#scope)
- [Defects fixed in the port](#defects-fixed-in-the-port)
- [The usability gate](#the-usability-gate)
- [Progress](#progress)
- [Setup log](#setup-log)
- [Decisions](#decisions)
- [Surprises](#surprises)

## Goal

A player or agent records a session with `--record`, and `--replay` later
re-runs it and gives an exact verdict: verified, or the first step that
diverged and why. A committed recording pins the engine's behaviour, so any
change to the rules fails until it is declared. Then the usability gate is
run and recorded, and the core is done.

## Scope

Ported from
[v0 at `3ecc396`](https://github.com/hoelzl/glyphwright-v0/tree/3ecc396).

| Area | S5 keeps | Later |
|---|---|---|
| Harness | `RecordingEngine`, `replay`, per-step event digests (`recording/1`), the rules revision in the header (`session/2`) | oracle and manifest terms (dropped with UE5) |
| CLI | `--record` (never overwrites), `--replay` | `:save`, `:load`, `:events` (v0 D8; deferred) |
| Tests | a committed reference-world recording that must replay | none |
| Docs | a replay-and-determinism page, decision 0003, four skills | none |
| CI | a job that runs the README quickstart literally on three systems | none |

## Defects fixed in the port

| ID | Defect | Fix |
|---|---|---|
| H2 | the engine version never changed, so replay's version check could never fire | a rules revision, written into every header and checked by replay; a pinned recording forces its bump (decision 0003) |
| H4 | the recording header is never validated, and the deleted `session/1` is still accepted | the header is checked key by key against `session/2`, and only `session/2` is accepted |
| H8 | a UTF-8 byte-order mark breaks replay with "the session header is not JSON" | recordings are read with the BOM stripped |
| H11 | a schema bump surfaces as "events diverged" at step 1 | a schema bump changes behaviour, so the pin forces a rules bump, and replay then reports the revision first |
| F7 | `--replay` was entangled with frontend checks it never uses | `--replay` refuses `--record` and `--seed` and ignores the frontend |

## The usability gate

From the [project brief](../../project-brief.md#core-done-the-usability-gate),
checked as the owner decided on 2026-10-21:

1. **Human:** the owner plays the README quickstart on Windows, timed; a CI
   job runs the README's quickstart commands literally on Windows, macOS, and
   Linux.
2. **Agent:** a fresh Claude subagent in a clean clone, told only the four
   tasks, uses `AGENTS.md` and the skills to author a two-area pack, get
   located diagnostics for a broken one, play it through JSONL, record and
   replay a session, and add an item kind with a test so that all gates pass.
3. **CI** passes on all three systems.

The verdicts go in the setup log below.

## Progress

- [x] Plan
- [ ] Rules revision and `session/2` header (H2, H4); decision 0003
- [ ] Recording and replay with exact verdicts (H8, H11)
- [ ] `--record` and `--replay` in the CLI (F7)
- [ ] The pinned reference-world recording
- [ ] Replay-and-determinism page; `AGENTS.md` route
- [ ] Skills: play-a-session, author-a-pack, add-an-item, pin-behavior-with-a-replay
- [ ] CI quickstart job
- [ ] Usability gate: agent run, owner run, CI
- [ ] Owner review of the S5 pull request
- [ ] Tag `s5` and the course tag; move this plan to `docs/plans/completed/`

## Setup log

Filled in as the slice proceeds.

## Decisions

- **A rules revision, pinned by a recording** (owner, 2026-10-21): an integer
  in the package names the engine's behaviour, separate from the release
  version. Every recording header carries it, and replay refuses a mismatch
  by name. A committed recording of the reference world must replay in CI,
  so a behaviour change fails until the revision is bumped and the pin
  re-recorded.
- **The usability gate is run by the owner on Windows, a CI quickstart job,
  and a fresh subagent** (owner, 2026-10-21).
- **Skills are written now.** The brief says a skill is written once a
  procedure has been done twice; each of the four has been done at least
  twice across S2 to S4, and the gate's agent needs them.

## Surprises

None yet.
