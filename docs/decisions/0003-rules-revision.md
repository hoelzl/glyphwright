# 0003 — A rules revision, pinned by a recording

How a recording names the behaviour that produced it, and what forces that
name to change. Read it before you change anything that alters what the same
commands produce, or when the pinned recording fails.

- **Date:** 2026-10-21
- **Status:** accepted

## Context

A recording is the engine identity, the pack id, the seed, and the commands;
replay re-runs the commands and compares each step's events. That only works
if the engine identity changes when the engine's behaviour does. In v0 it
never did: the version stayed `0.1.0` across about 27 behaviour-changing pull
requests, so replay's version check could never fire, and a behaviour change
surfaced as a misleading "events diverged" (v0 findings H2 and H11).

The release version cannot carry this. Releases happen when someone decides to
publish; behaviour changes whenever a rule, a message, or a wire shape does.

## Decision

- **An integer rules revision**, `RULES` in
  `src/glyphwright/harness/fingerprint.py`, names the behaviour. Every
  session header carries it, and replay refuses a recording made under
  another revision, naming both.
- **A committed recording pins it.** A recording of the reference world under
  `tests/recordings/` must replay in the test suite. A change that alters
  events, frames, or state makes it diverge, and the failure says to bump
  `RULES` and re-record the pin.
- **A wire-schema bump is a behaviour change.** The event digests include the
  schema tag, so the pin catches it like any other change.

## Consequences

- A behaviour change is a two-line diff anyone can see in review: the
  revision bump and the re-recorded pin.
- Every recording made before a bump stops replaying, with a message that
  says why. Until an outside consumer keeps recordings, that costs nothing.
- The pin only covers what its script exercises. It is a tripwire for
  accidental change, not proof that nothing changed; the property walks and
  goldens cover the rest.
