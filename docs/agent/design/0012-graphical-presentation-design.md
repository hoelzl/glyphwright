# Graphical Presentation — Design Document

| | |
|---|---|
| **Status** | Substrate C ratified 2026-07-19 (14D, §7) — subordinate to `0003`; revises `0003` §2 Goal 1's framing (§1) and §2 Goal 3's determinism contract (§6, when an oracle is consulted); supersedes `0011`'s scope where they disagree (§1, §9). The §6 two-tier oracle contract is **pinned** (coarse oracle fingerprint + drift-detection audit + corrections-as-events, §11.5) and anchor fidelity is resolved (§11.1); its `glyphwright.session/2` implementation is 15A's remaining work (§10) |
| **Date** | 2026-07-18 |
| **Scope** | What "a person enjoys playing it" means for the architecture: the three-observer model, the SceneGraph seam, click-to-move with the two-tier oracle model, decoration, and the 2D/in-repo-3D/UE5 substrate decision — with the UE5 MCP probe as decision evidence |
| **Authority** | `0003` wins on any disagreement outside the two premises this document explicitly revises (§1 framing, §6 determinism); this document supersedes `0011` §7's "usability claim" |

## 1. Purpose: revising the frame, not just the renderer

`0011` shipped a GUI that is a faithful copy of the TUI. It proved the pipeline
works — pure `compose`, headless goldens, grammar-minted input — and it is, by
the owner's assessment, not a game a person would choose to look at. That
assessment is the starting point of this document, and it exposes a framing
error that predates the GUI: `0003` §1 declares GlyphWright **"terminal-first
and agent-drivable,"** and product-vision.md repeats it, because the project
grew out of the Recursive://Neon finding that agents reason best over text.
That was the right conservative answer at the time. It is not the product
question.

The product question, restated: **can GlyphWright present a turn-based RPG that
feels the way a player expects — an animated character, click-to-move
pathfinding, a world worth looking at — while remaining agent-explorable in a
way that validates the human's outcome, not a different outcome?** This document
adopts that question as the design's center. "Terminal-first" survives only as
the historical fact that the *verification* surface was built first; it is no
longer a claim about what the game is. The engine's architecture was already
pointing past the terminal: `0003` line 54 requires grid worlds to be
"presentable as 2/2.5/3D in other frontends," and product-vision.md says tile
structure is "a semantic modeling tool, not a mandate that every presentation
look like a tile map."

This revision is a scope decision by the owner, recorded here because `0003` is
the specification and a change to its §1 framing must be written, not implied.
Nothing else in `0003` is weakened: determinism, the transition boundary,
frames-as-evidence, and the TermVerify independence (§16, ADR-001) are
unchanged and load-bearing for everything below.

## 2. The three-observer model

The design centers on three ways of observing one engine, each with its own
evidence:

| Observer | Who | Evidence | Surface |
|---|---|---|---|
| **Agent** | TermVerify, an LLM driver | Semantic frames + typed events (deterministic, replayable) | `glyphwright.api`, JSONL/plain — **exists** |
| **Human** | A player | Rendered presentation: 2.5D/3D scene, animation, click-to-move | a presentation frontend — **this document** |
| **Bridge** | A verifier that the two agree | Projection-consistency + recorded sessions replayed through both | scene/scene-graph goldens — **exists in 2D, extended here** |

The bridge is the load-bearing member and the one the current GUI fails to
reach far enough. The methodology's claim is not "we can render something" but
"the agent's interaction and the human's interaction are two projections of the
same run, and we can *prove* it." Every substrate decision below is judged by
whether it strengthens or weakens the bridge.

## 3. The SceneGraph seam

`0011` §3's decision — "the Scene is the evidence, the pixels are derived
material" — is correct and is retained; it is the same relationship frames have
to ANSI output in `0003` §11. What changes is the *shape* of the evidence. A
flat cell grid cannot express "the ground persists under the player," let alone
a 3D diorama. The presentation core therefore becomes:

```python
def compose(frame, manifest) -> SceneGraph: ...
```

`SceneGraph` is frozen, pygame-free, engine-free data naming everything the
presentation will realize:

- **placements** — `(semantic_pos, render_pos, asset_id, tier)` for every
  visible entity and every terrain/fixture tile in the viewport, ordered;
- **tier assignments** — which compositing tier each placement occupies
  (§4: ground / fixture / actor), derived at compose time, never
  re-derived by the painter; **z-level** rides as part of `render_pos`,
  not as a tier;
- **camera** — a deterministic function of the viewport and the frame, not of
  wall-clock input (§7);
- **transition descriptors** — for each event in the frame's log delta, a
  cosmetic animation directive (move, strike, spawn, despawn) the painter may
  interpolate between the prior and current SceneGraph (§6);
- **input affordances** — the click targets, minted from the `CommandGrammar`
  exactly as `0011` §4 already does, now expressed as projections into the
  scene (§6).

Everything downstream is a thin `realize(scene_graph, backend)` that draws it;
only `realize` and the event pump import a rendering substrate. The split is
unchanged in kind from `0011` — goldens and projection-consistency run with no
renderer installed — but the evidence is now a scene graph, not a cell grid.
The `manifest` (§5) is new input, and because `compose` reads it, the manifest
is part of the determinism contract: it is hashed into the presentation
fingerprint alongside the pack hash.

## 4. Tiers vs. z-levels: a vocabulary commitment

Two different concepts both want the word "layer." Conflating them is the
fastest route to a confused implementation, so this document assigns each a
distinct term up front and uses them consistently:

- A **tier** is a *compositing* concept — the painterly stacking of
  things at one position: ground / fixture / actor. A cell has tiers.
  Tiers are cosmetic: they exist so the player can stand *on* the ground
  rather than replacing it. Tier assignment is decided at `compose` time
  (§3) and is what the immediate defect — the ground disappearing under
  the player — is fixing.
- A **z-level** is a *spatial* concept — a distinct horizontal slice of
  the world that is physically several meters above or below another.
  A position has a z-level. Z-levels are semantic: `village:7,3,2` is
  a different place than `village:7,3,1`, the second floor of a tower is
  a z-level above its ground floor, and stairs connect them. Z-levels
  live in the world model and the kernel, not in the painter.

Tier and z-level are orthogonal. A position identified by z-level 2 has
its own ground/fixture/actor tiers within that z-level. A z-level
transition (climbing stairs) is an explicit kernel exit (`up`/`down`);
a tier transition (the player walking onto a tile that already has a
floor) is not a transition at all, only a compositing decision. The
SceneGraph carries z-level as part of `render_pos` and tier as a
separate field, so a reader of the scene data can never mistake one for
the other.

### 4.1 Tiers are a frame-model change

The compositing defect is that `GridView` models the world as one glyph
per cell, so there is nowhere for "floor" and "actor on the floor" to
coexist. Fixing it is a **frame-model change at the source**, per
`0011` §1's rule that a missing capability is fixed in the frame, never
worked around in a frontend:

- `GridView` moves from `tiles: tuple[str, ...]` to a **tiered cell
  model** — ground / fixture / actor — so one cell names its terrain,
  any structure on it, and any actor standing there. This bumps the
  `glyphwright.frame` wire tag (§15's schema-versioning rule), and
  plain/TUI must project the tiers back to their single-glyph surface
  with a declared precedence (actor over fixture over ground), which
  widens `project` deliberately (§17's rule that widening the
  transcript is a visible change).
- The tiered frame is required by every substrate below, 2D or 3D, so
  it is not wasted work whichever way the substrate decision lands.

### 4.2 Z-levels are not implemented

`0003` §7.2 already defines `PosId = (x, y)` **or `(x, y, layer)`** with
stairs/ramps as explicit `up`/`down` exits; that `layer` is a z-level
under this document's vocabulary, and it remains an unimplemented spec
feature. This document does not implement z-levels; it only reserves the
term so that future work on multi-floor worlds does not collide with the
tier system the presentation needs today. Until then, every `PosId` in
every pack carries an implicit z-level of 0.

## 5. The presentation manifest

Rendering a real asset pack needs a mapping the engine does not have: which
image or mesh stands for "floor," what decorates a wall, how big a tile is on
screen. That mapping is content, not code, and it is **not** the semantic
source of truth. A new **presentation manifest** — TOML, version-controlled,
living beside the content pack (or as a pack sidecar) — carries:

- **asset bindings**: semantic tile/entity kind → asset reference (an image for
  a 2D pack, a mesh + material for a 3D pack), with the pack's CC0 provenance
  recorded per `0002`'s standard;
- **decoration policy**: seeded, deterministic placement of non-semantic
  ornament (rubble, grass tufts, wall variation), drawn from the run seed or a
  manifest-declared seed — decoration is derived material, never kernel state,
  so it can never make two replays of one command stream disagree;
- **presentation hints**: tile footprint, camera framing preferences, palette.

Because `compose` reads the manifest, the manifest participates in determinism:
its hash joins the presentation fingerprint, so "same seed, different manifest"
is detectably a different presentation — the presentation-side analogue of
`0003` §8.2's pack-ID rule.

## 6. Click-to-move and animation are presentation, compiled to the kernel

Two features the player expects have engine consequences that must be stated
honestly, because they are where "presentation" could silently leak a wall
clock into the interaction loop:

- **Click-to-move is a macro-command, not new kernel behavior.** The player
  clicks a reachable position; the frontend expands that into a deterministic
  sequence of `move <exit-token>` commands via a pure pathfinding function
  (A* over the grid's passable topology, with seeded tie-breaking), each step
  validated by the kernel. The agent never needs the macro — it sends single
  moves — and the human's session stays perfectly replayable because the
  expansion is deterministic and the resulting event stream is identical to
  having typed the moves. This is the general pattern this document commits
  to: **presentation-side convenience that compiles down to the existing
  command grammar, never new kernel semantics.**

  **The pathfinding-origin decision: GlyphWright owns it; UE5 may serve as
  oracle.** An earlier draft of this section resolved the pathfinding-origin
  question by forbidding UE5's NavMesh from contributing to navigation at
  all — waypoints always from GlyphWright's pure grid pathfinder, the
  presentation host executing them literally with no repathing. That was
  overcorrecting. It would have required forbidding UE5's collision system
  too: the moment a UE5 wall does not perfectly align with a semantic-grid
  wall tile — and such drift is the *normal* case, because level geometry
  and grid topology will always disagree at the margins — a character
  executing straight-line segments between grid waypoints clips the wall,
  gets stuck, and enters a state the semantic model cannot see. Declaring
  the drift forbidden does not make it go away; it just makes the failure
  unattributable. The framing was also built on a premise this project does
  not hold: that "the kernel does everything with no external input" is a
  goal. It is not. ADR-001 (`0003` §16.1) is about *import-time*
  independence — the shipped package works with TermVerify absent — and
  says nothing about whether the engine may *consult* an external oracle at
  runtime. TermVerify's whole purpose is to extract desired behavior from
  an external oracle and verify the implementation against it, so a
  GlyphWright that can consult UE5 as an oracle is more aligned with that
  model, not less.

  This document therefore adopts a **two-tier oracle model** for
  navigation and collision:

  - **Tier 1 — kernel-internal pathfinder (deterministic, always
    available).** GlyphWright's pure A* over the semantic grid produces
    the canonical waypoint sequence. This is the pathfinder used before
    any UE5 level exists, during headless agent operation, for
    investigations that do not depend on level-geometry details, and as
    the reference output the bridge compares against. It is fully
    deterministic and requires no external process.
  - **Tier 2 — UE5 as oracle (matches the rendered game).** When a UE5
    level is loaded, GlyphWright may *consult* UE5's navigation and
    collision systems to resolve questions the semantic grid cannot
    answer accurately — most importantly, whether a candidate path
    segment collides with actual rendered geometry, so the reported
    behavior matches what the human player sees. The result feeds back
    into the semantic observation: if UE5 reports a collision the grid
    did not predict, that is evidence of grid/level drift to be
    reconciled, not a silent discrepancy.

  Two consequences follow, and are accepted deliberately:

  - *Non-determinism enters through the oracle, and that is manageable,
    not forbidden.* A Tier-2 consultation introduces behavior that
    depends on UE5's current state (level build, NavMesh version, plugin
    version). Rather than treat this as a violation of determinism, the
    project treats it as a fingerprint input: an oracle-consulting run
    records *which oracle* it consulted alongside the seed and command
    stream, so two runs against the same oracle reproduce, and a run
    against a different oracle is detectably different — the same shape
    TermVerify gives to any external oracle. The determinism contract
    becomes "same `(pack, seed, commands, oracle-fingerprint)` ⇒ same
    frames," with oracle-fingerprint optional and empty for Tier-1 runs.
    This is a narrower, more honest contract than "always deterministic
    regardless of oracle"; it is what TermVerify already assumes. **The
    oracle-fingerprint is coarse** (§11.5): the level path, the UE5/plugin
    version, and the set of bound semantic-position keys, as one opaque
    hashed string — cheap to compute, stable across cosmetic edits.
    Collision-geometry drift is *not* encoded in the fingerprint; it is
    caught by an explicit, on-demand drift-detection audit (§11.5), not by
    per-run fingerprinting.
  - *The bridge compares runs, not absolute truth.* The bridge's job is
    not "the semantic path is correct" but "the agent's observation and
    the human's observation agree given the oracle they each used." An
    agent operating headless uses Tier 1; a human playing through UE5
    uses Tier 2; the bridge replays the human's recorded click sequence
    through Tier 1 and checks that the resulting `PosId` sequence
    matches, *flagging* any cell where Tier 2's collision correction
    moved the character off the Tier-1 path as a grid/level drift to
    investigate. Disagreement is signal, not failure. **A Tier-2
    collision correction is recorded as a durable, typed event in the
    session log** (§11.5), so replay reproduces it exactly from the
    record rather than re-consulting UE5 — necessary because the coarse
    fingerprint does not determine collision answers.

  UE5's NavMesh and collision are therefore first-class navigation
  inputs when available, not forbidden resources. GlyphWright's pure
  pathfinder remains the deterministic backbone and the always-available
  fallback; UE5 is an oracle that makes the reported behavior match the
  rendered game, at the cost of an oracle-fingerprint term in the
  determinism contract. The earlier "straight-line execution only,
  NavMesh never used for navigation" framing is withdrawn.
- **Animation is cosmetic interpolation over the frame stream.** A move is
  rendered as a tween between the prior and current SceneGraph placements; a
  strike as a flash. Input is accepted at frame boundaries, never gated on an
  animation finishing — the engine stays turn-based to its foundations, and
  turn count remains the only time (`0003` §5). A `skip-animation` flag makes
  the presentation as fast as the TUI, which is what lets a recorded session
  be replayed through the presentation frontend for verification without
  waiting out tweens.

## 7. The substrate decision, and its evidence

Three substrates can realize the SceneGraph. The choice is a dependency/CI
decision under the completion contract, so the rationale and the evidence are
recorded here.

| Substrate | Strength | Cost / risk |
|---|---|---|
| **A. pygame-ce, layered 2D** (current stack) | Zero new substrate risk; dummy-driver headless CI is proven (`0011` §2); Kenney 2D packs drop in | A hand-rolled 2.5D in pygame is a dead end if 3D is later wanted — the painter is rewritten |
| **B. In-repo Python 3D** (moderngl / pyglet) | Real depth buffer gives occlusion for free; Kenney low-poly kits (retro-fantasy, fantasy-town) map onto a grid | Headless GL in CI needs osmesa/EGL setup; new runtime dep needs a pinned/offline story meeting `0011` §2's standard |
| **C. UE5 as an external presentation host** | Epic is building the semantic seam *into the engine*; occlusion, lighting, assets, and camera are free | Not pinnable/offline; a running editor is the test fixture; plugin is *Experimental*; ruled out as the verification substrate |

**Decision: pursue C (UE5) as the primary human-facing path, with A (pygame)
as the guaranteed headless fallback.** This document commits to that direction
and does not hedge: C is the path until a concrete blocker forces a
re-evaluation, at which point B (in-repo Python 3D) becomes the next option
before falling all the way back to A. The deciding evidence is a live probe of
the owner's UE5.8 instance (2026-07-18, recorded in §8): the official Unreal
MCP plugin is not a generic geometry API — it is building exactly the
agent-facing seam this design needs, via `AgentWorldToolset` anchors. B is
named as contingency rather than evaluated up front because paying its
headless-GL/CI cost is only worthwhile if C actually fails.

**Ratification (14D, 2026-07-19).** C is **kept** as the human-facing path.
14C converted the §8 hand-probe into a reproducible, version-controlled
capability and verified it against the running editor: an isolated
`frontends/presentation/ue5` package (its own `ue5 = ["mcp"]` extra, excluded
from the bare CI job exactly like the GUI), an async MCP client over the
plugin's meta-tools, a pure deterministic `SceneGraph → SpawnOp` importer, and
an opt-in e2e that performs the real round-trip — level query, semantic-anchor
listing (each anchor carrying `worldStateKey`), a spawn+remove, and a posed
`CaptureViewport` → PNG. The §8 loop is no longer a one-off finding; it is a
tested seam. Two scope facts temper the ratification and are carried into
§10/§11 rather than hidden: at 14D the anchor-*fidelity* and oracle-*identity*
questions were still open (14C listed anchors but never set one carrying a
GlyphWright semantic position, and no navigation-drift case had been run), so
the two-tier oracle model of §6 was adopted in principle but not yet exercised.
Both questions are **resolved in 15A** (§11.1, §11.5): anchors carry semantic
positions via the world-state file, and the oracle fingerprint is coarse with
corrections recorded as events. No code consults UE5 for navigation or collision
yet — that is 15A's `glyphwright.session/2` implementation — but the contract it
encodes is now pinned. C is ratified as the *presentation* path; the *oracle*
role of §6 Tier 2 is no longer provisional, only unimplemented.

## 8. Decision evidence: the UE5 MCP probe

A throwaway probe (not committed) drove the running editor over MCP at
`http://127.0.0.1:8000/mcp` (protocol `2025-11-25`, streamable-HTTP/SSE, the
official Python `mcp` client). Findings:

- **Surface.** Three meta-tools (`list_toolsets`, `describe_toolset`,
  `call_tool`) front ~60 toolsets. The relevant ones: `SceneTools`
  (`load_level`, `find_actors`, `add_to_scene_from_class/asset`,
  `remove_from_scene`), `EditorAppToolset` (`GetCameraTransform`/
  `SetCameraTransform`, **`CaptureViewport`** returning PNG base64,
  `WorldPosToScreenCoords`/`ScreenCoordsToWorld`, `StartPIE`), and
  `SlateInspectorToolset` (Playwright-style `Screenshot`/`Click`/`Snapshot` of
  the editor UI).
- **Confirmed loop.** The probe read `/Game/Maps/EmptyOpenWorld1` (**421
  actors** enumerated as structured soft-path refs), positioned the camera over
  the wire, and captured a 1.5 MB viewport PNG — scene query, camera control,
  and pixel evidence, all from outside the process.
- **The decisive finding.** `AgentWorldEditor.AgentWorldToolset` provides
  semantic **anchors** — Epic's own binding layer between "textual world state
  and level geometry," with World Partition actor-descriptor queries that see
  *unloaded* cells. The semantic scene graph this design needs is not something
  we would fight UE5 to obtain; Epic is building it for the same reason we want
  it. That moves C from "possible but adversarial" to "aligned."
- **Constraints.** The plugin is Experimental ("APIs and data formats subject
  to change"), localhost/single-client (calls serialize on the game thread),
  and requires a running editor — so it can be a *presentation host* but never
  the *verification substrate*. TermVerify + GlyphWright's semantic frames
  remain the authoritative evidence; the UE5 viewport is the human-facing
  artifact and the bridge's screenshot source.

## 9. Architecture under substrate C, and what happens to 0011

Under C, the three-tier mapping is explicit:

- **Source of truth stays in GlyphWright packs** — grid topology, barriers,
  portals, spawns, encounter tables (the answer to "where does navigation live"
  is: *never in the 3D scene*; making the scene authoritative would destroy
  determinism and the replay contract).
- **The manifest (§5) maps packs to UE5 assets.** An **importer** reads a pack
  + manifest and scaffolds a UE5 level via the MCP scene tools — spawning
  actors, placing geometry, tagging anchors. This is a *build-time / preview*
  tool, deliberately isolated: it is the first component here that is not
  fully offline/pinnable, so it lives behind its own extra, is excluded from
  the bare CI job like the GUI (`0011` §6), and is never imported by the core
  — the same mechanical-isolation pattern ADR-001 uses for TermVerify.
- **Evidence flows back.** A recorded session replays through the presentation
  host; the host projects `find_actors` + transforms into a scene-graph golden
  and `CaptureViewport` into a human-reviewed screenshot. The agent's `move
  north` and the human's click must produce the same `PosId` transition and the
  same scene-graph checkpoint — that equality *is* the bridge, and it is the
  Recursive://Neon `parity/` harness one level up.

**Who edits the 3D world.** Both the agent and the human, but reconciliation is
a **data merge, not a live sync**: the human may edit in the editor, the agent
may regenerate via MCP, and an import step brings either side's changes back to
the manifest (or rejects them). The scene is regenerated from the manifest, so
it is never the thing two editors fight over.

**Consequences for 0011.** This document supersedes two of its claims:
`0011` §7's "13B completes the usability claim" is **retired** — parity with
the TUI is not usability, and the owner's critique is the evidence; and
`0011` §8's pixel-hash open question is **absorbed** — under substrate C the
pixel evidence is a reviewed `CaptureViewport` screenshot, and under A the
"paints-without-error + scene goldens" contract of 13A stands, so no committed
cross-platform pixel baselines are added in either case. The in-repo pygame GUI
(13A–13C) is retained as the guaranteed headless fallback and the place where
the tiered frame (§4) is first exercised; the 13C tileset flag is the natural
home for a *real* CC0 2D pack (Kenney roguelike-rpg) to validate tiering
against real assets rather than the 13 placeholder tiles.

## 10. Slices

Following the 9A/9B and 13A/13B precedent: one design, ordered slices, each
landing with tests and docs, later slices re-scoped by what earlier ones learn.

- **14A — Tiered frame.** `GridView` gains compositing tiers (§4); plain/TUI
  project with declared precedence; frame wire tag bumps; the pygame GUI renders
  the tiers (fixing ground-under-player); a real CC0 2D pack drives `--tiles`.
  Substrate-independent — required by every path.
- **14B — SceneGraph + click-to-move.** `compose(frame, manifest) ->
  SceneGraph` with goldens parallel to the 13A scene goldens; deterministic
  path-expansion with a replay test proving a click-session replays
  byte-identically through JSONL (§6); presentation manifest with its hash in a
  presentation fingerprint (§5).
- **14C — UE5 importer + preview (isolated).** The MCP client behind its own
  extra; scaffolding a level from a pack + manifest; viewport-capture evidence;
  excluded from the bare job; verified against a running editor, which is the
  fixture — an opt-in e2e mark, never part of the standard suite.
  *Scope note (14C): the §5 manifest-term and §6 oracle-term in the session
  fingerprint are a versioned-protocol change to the `glyphwright.session/1`
  header and its committed schema. Per the completion contract (no replay/
  protocol change without a written rationale and review) and the standing
  gate that protocol/evidence decisions are human-reviewed, that change was
  **deferred to 14D**; 14D in turn moved it to 15A, where the oracle model it
  encodes is pinned as a design decision and its fingerprint terms await
  ratification in the `session/2` schema (see the 14D Resolution below).
  14C ships the client, importer, and opt-in e2e without it.*
- **14D — Substrate decision ratified.** On 14C's evidence, either keep C as
  the human-facing path (updating this section) or fall back to A and scope B.
  ~~*Also owns the deferred fingerprint terms above: if C is kept, bump the
  session schema to carry the optional manifest and oracle fingerprints (§5/§6),
  with the written rationale recorded here.*~~

  *Resolution (14D, 2026-07-19): C is kept — see §7's Ratification. The
  deferred fingerprint terms are **moved out of this slice**, not landed here:
  bumping `glyphwright.session/1` is a replay/protocol-contract change, and at
  that date the §6 oracle model it would encode was not yet evidenced — neither
  the anchor-fidelity question (§11.1) nor the oracle-identity/correction-replay
  question (§11.5) had been resolved against a live editor, and both gate what
  a stable oracle fingerprint even *is*. Writing the schema field before that
  evidence would encode a guessed contract into a versioned protocol. The
  fingerprint work is therefore deferred to the oracle-model slice below (15A),
  which would resolve §11.1/§11.5 first and only then ratify the fingerprint
  terms (both since resolved in 15A). 14D ships as a documentation-only
  ratification.*
- **15A — Oracle model + session fingerprint (protocol change).** The two
  live-editor questions are now **resolved** (§11.1, §11.5, both 2026-07-19):
  anchors carry semantic positions via the world-state file, and the oracle
  fingerprint is coarse (level path + plugin version + semantic-position set)
  with collision drift caught by an explicit audit and corrections recorded as
  events. What remains in the slice is the *implementation*: bump the session
  schema to `glyphwright.session/2` carrying the optional manifest and oracle
  fingerprints (§5/§6) plus the typed correction event, with the written
  rationale recorded here and the replay-compatibility story reviewed per the
  completion contract. This is the slice where UE5 first becomes a
  *navigation/collision oracle*, not just a presentation host.

## 11. Open questions

*State after 15A evidence-gathering (2026-07-19): the substrate decision is
ratified (§7). §11.1 (anchor fidelity) and §11.5 (oracle-fingerprint identity +
correction replay) are now RESOLVED — §11.1 by a live world-state-file round-trip,
§11.5 by a live `trace_world` collision probe plus a design decision (coarse
fingerprint + explicit drift-detection audit; record corrections as events).
§11.2 (editor-in-CI) remains open; §11.3 (B's headless story) and §11.4
(z-levels) stay dormant.*

1. **Anchor fidelity** — whether UE5's `AgentWorldToolset` anchors can carry
   GlyphWright's semantic positions (`village:7,3`) as first-class anchor
   identities, or whether the importer must maintain the mapping externally.
   **RESOLVED (15A, 2026-07-19): first-class, via a world-state file.** There is
   no MCP anchor-write tool — the toolset's whole surface is `ListAnchors`,
   `ValidateAnchors`, `Solve`, `RefreshConstraints`, `LoadRegion`,
   `ListActorDescriptors`. The binding surface is the engine-authoritative file
   `WorldState/<MapShortName>.json` (vocabulary v1, documented in
   `WorldState/SCHEMA.md`): a `locations` object keyed by the semantic id
   (`village_7_3`), each `{kind, size, inside?, adjacentTo?, description?}`,
   plus `bindings` mapping `key → anchorId guid`. Verified live: authoring such a
   file made `RefreshConstraints` report `loaded:true, locations:N, bindings:M`
   (unbound keys flagged with a warning), and a bound key surfaced in
   `ListAnchors` as `worldStateKey: <key>`. So a GlyphWright semantic position
   becomes a first-class anchor identity by the importer *authoring the file* —
   location key + spawn `LayoutBox` + record `bindings[key]=guid`. The mapping is
   internal to the engine, not maintained externally.
2. **Editor-as-fixture in CI** — whether the 14C e2e can run on a self-hosted
   runner with UE5 installed, or stays a local-only opt-in. **Still open.**
   Affects how much of the bridge is continuously verified vs. run on demand.
   Not blocking 15A's protocol change, but it gates whether 15A's oracle
   evidence can be reproduced in CI or only locally.
3. **B's headless story** — if C falters, what osmesa/EGL costs the matrix
   across both OSes before B is viable. Not worth answering until C's outcome
   is known; C was ratified in 14D, so this stays dormant unless a concrete
   blocker forces re-evaluation.
4. **Z-levels** — whether any near-term content wants `0003` §7.2's
   `(x, y, layer)` PosId; deferred until a pack needs stairs, as it has been.
5. **Oracle-fingerprint identity and replay semantics (from §6).** The
   two-tier oracle model widens the determinism contract to
   "same `(pack, seed, commands, oracle-fingerprint)` ⇒ same frames."
   **RESOLVED as a design decision (15A, 2026-07-19), on live evidence.** The
   drift *detector* was confirmed against the running editor
   (`SceneTools.trace_world`: a ray through a collision-enabled cube wall
   returns the hit distance, e.g. `800`; a ray beside it returns `null`; only
   geometry with a collision mesh registers, so spawn the collision *asset* —
   `add_to_scene_from_asset` with `asset_path` — not the bare class). The two
   sub-questions resolve as follows:

   - *Identity → coarse fingerprint + an explicit drift-detection step.*
     The oracle fingerprint in the session header is **coarse**: the level
     path, the UE5/plugin version, and the set of bound semantic-position keys,
     recorded as one opaque hashed string. It answers "is this the same map,
     same plugin build, same set of semantic positions?" — cheap to compute,
     stable across the cosmetic edits (lighting, materials, non-navigation
     tweaks) that must not invalidate recordings. What it deliberately does
     *not* encode is collision geometry, because the fine alternative — hashing
     `trace_world` results over the grid's passable edges — was rejected: it is
     O(grid) per fingerprinted run, untenable on large maps, and its continuous
     hit-distances (or any float-normalization) would over-invalidate
     recordings on trivial geometry nudges. Collision-drift detection is
     instead a **separate, explicit audit step** (re-`trace_world` the
     passable-edge set and diff against expectation), run on demand — with the
     option to auto-trigger it later if we hit false-positives where a same-
     named, same-positions map has nonetheless drifted. This keeps the per-run
     contract cheap and puts geometry-drift detection where it can be scoped
     to a region of interest rather than every recording's identity.

   - *Correction replay → record the correction as an enriched session
     event, never re-derive it.* Because the fingerprint is coarse, the oracle
     is *not* a pure function of it (a NavMesh rebuild or a sub-position
     geometry nudge can change a trace answer without moving the fingerprint),
     so re-deriving a Tier-2 correction from the fingerprint alone would be
     unsound. A Tier-2 run that consults UE5 and receives a collision
     correction records that correction as a durable, typed event in the
     session log — like any other event — so replay against the same
     `(pack, seed, commands, oracle-fingerprint)` reproduces the correction
     exactly without re-consulting UE5. Re-consultation on replay is reserved
     for the explicit drift-detection audit, not for ordinary replay.
