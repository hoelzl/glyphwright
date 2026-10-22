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
- [x] Rules revision and `session/2` header (H2, H4); decision 0003
- [x] Recording and replay with exact verdicts (H8, H11)
- [x] `--record` and `--replay` in the CLI (F7)
- [x] The pinned reference-world recording
- [x] Replay-and-determinism page; `AGENTS.md` route
- [x] Skills: play-a-session, author-a-pack, add-an-item, pin-behavior-with-a-replay
- [x] CI quickstart job
- [x] Usability gate: agent run, owner run, CI
- [ ] Owner review of the S5 pull request
- [ ] Tag `s5` and the course tag; move this plan to `docs/plans/completed/`

## Setup log

- Commits, in order: plan; rules revision and header check (decision 0003);
  recording and replay; CLI; the pin; replay page; skills; CI quickstart;
  then the fixes from the agent gate.
- New structure: `tests/recordings/` for the pin, `.agents/skills/` with four
  skills, and their generated stubs in `.claude/commands/`. The planned-path
  entries for those folders are gone now that they exist.
- New gate: versioned schema tags are refused in current prose, after the
  agent gate's run left one stale in a skill.
- Not added: a programmatic replay API in `glyphwright.api`. The CLI is the
  surface the gate and the skills use; nothing asked for more.

### Gate record

- **CI, item 3:** every leg green on the draft PR, including the new
  quickstart job on Windows, macOS, and Linux (item 1, mechanical half).
- **Agent, item 2:** a fresh subagent in a clean clone of this branch,
  given only the four tasks, passed all four. It wrote a two-area pack from
  scratch and got `entities.toml:16: entity 'stairs-up': portal leads into a
  wall: attic:0,0` for a broken portal. It played the pack through JSONL
  across both areas, recorded and replayed it (`recording verified: 3 steps,
  turn 3`), and showed the divergence, rejection, pack, and rules verdicts.
  It added a recall item, a new `Recalled` event, and tests, and the check
  passed. It needed source code only for the engine task, as expected. It
  reported nine shortfalls in the guidance; all are fixed in the two commits
  after the CI job.
- **Owner, item 1:** passed on 2026-10-22. Setup took about two minutes;
  two games took a little over ten. Four findings, all fixed in one commit
  after the gate: an item under the player was hidden by the player's glyph
  and named nowhere; only a failed `take` said what could be taken; nothing
  said a sword is equipped rather than used; and portal exits such as
  `down` showed only after a move failed. Frames now carry `here` and the
  open `exits`, a bare verb lists its choices, `use` on equipment points to
  `equip`, and the plain frontend reprints the command list when it
  changes.

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

- **The pin's advice was wrong in the gate's own case.** Adding a component
  to `Entity` changes every pack id, so the pin failed on the pack before it
  reached the events, and advised "only re-record" for a change that also
  bumped the event tag. The test now replays the steps against the new id to
  tell the two apart.
- **The skills held a volatile fact.** The play-a-session skill named
  versioned schema tags; the agent's change made them stale at once. That is
  rule A7, now a gate.
- **The agent passed where the person stumbled.** The agent read the
  grammar in every JSONL frame and never missed an item or an exit; the
  plain transcript left the same grammar out as machine detail, and a
  person playing by eye had nothing to read it from. The frame now says
  what is here and where you can go, for both.
- **The digests do not cover frames.** The first draft of decision 0003 said
  the pin caught frame changes; it does not, and the goldens do instead.
