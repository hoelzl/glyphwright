# Graphical Frontend — Design Document

| | |
|---|---|
| **Status** | Accepted 2026-07-18 — subordinate to `0003`. Substrate and slice split agreed with the user 2026-07-18 |
| **Date** | 2026-07-18 |
| **Scope** | Adds a graphical frontend as slices 13A–13C; records the project's first runtime-dependency rationale |
| **Authority** | `0003` wins on any disagreement; this document only refines it |

## 1. Purpose

Every existing frontend targets the terminal. The strategic point of a graphical
frontend is different from theirs: to prove that GlyphWright's agent-driven
development process yields software that is genuinely *usable by people*, not
merely verifiable and extensible by agents. The GUI is therefore judged by two
standards at once — a person must enjoy driving it, and an agent must be able to
verify it with the same rigor as the plain transcript.

Nothing in the engine changes. The GUI is a fourth frontend in the `0003` §12
list: a pure consumer of `SemanticFrame` (§11) that translates input events into
the same semantic commands every other frontend sends (ADR-003). If building it
reveals a missing capability, that is a frame or API gap to fix at the source —
never a GUI-side workaround (§14's rule for adapters applies unchanged).

## 2. Substrate decision: pygame-ce, as an optional extra

**Decision.** The GUI is built on **pygame-ce** (SDL2-based, community edition),
declared as the optional extra `glyphwright[gui]`. The core package keeps zero
runtime dependencies; `pip install glyphwright` is unaffected.

This is the project's first runtime dependency, so the completion contract
requires the rationale in writing:

- **Fully pinned, self-contained wheels.** pygame-ce bundles SDL2 and its
  satellite libraries inside platform wheels for Windows (x64/ARM64), macOS
  (universal2), and manylinux. `uv sync --locked` therefore yields a
  hash-verified, offline-installable environment — the same reproducibility
  standard the rest of the toolchain meets. No component downloads anything at
  runtime.
- **Proven headless rendering.** `SDL_VIDEODRIVER=dummy` renders real surfaces
  without a display — the CI path is long-established and widely exercised, so
  the painted output is testable on every runner in the existing matrix.
- **Maturity.** Production/Stable, actively maintained community governance,
  frequent releases (2.5.7, 2026-03), CPython 3.10–3.14 — covering this
  project's 3.12+ window with headroom.
- **Right-sized API.** Surfaces, blitting, font rendering, and an event pump
  are exactly the small subset a glyph/tile grid needs.
- **License.** LGPL-2.1-or-later, used as an unmodified dependency — compatible
  with GlyphWright's Apache-2.0 distribution; no source is copied, so no
  provenance obligations arise beyond this note (the `0002` standard).

### 2.1 Alternatives evaluated and rejected

- **PySDL3 (direct SDL3 bindings, evaluated 2026-07-18 at the user's request).**
  Rejected on packaging grounds: PySDL3 downloads SDL3 binaries from a GitHub
  repository *at first run*, which defeats lockfile pinning, breaks offline
  installs, and adds a supply-chain surface to every fresh CI runner — in
  direct conflict with the determinism discipline the project is built around.
  The custom-binaries escape hatch would make building and pinning SDL3 per
  platform this project's problem. Secondary grounds: beta maturity (0.9.x,
  effectively single-maintainer) and a raw C-style API that costs more code for
  the same grid. Its one real advantage — SDL3 today rather than SDL2 — buys
  nothing a deterministic tile grid needs, and the scene seam (§3) confines any
  future pygame-ce 3.x/SDL3 migration to one module.
- **tkinter.** Nominally stdlib, but Tk is absent from common
  python-build-standalone/uv-managed interpreters, so "zero dependencies"
  would become a soft claim while headless CI (Xvfb) and unhashable painted
  output weaken verification.
- **Web frontend (stdlib server + browser canvas).** Keeps the Python side
  dependency-free but imports an HTML/JS code surface, a browser as de-facto
  runtime, and a second testing toolchain — a larger total-complexity bill
  than one well-bounded extra.
- **PySide6/Qt.** Hundreds of megabytes and a widget model this design does
  not use; only justified by a desktop-app ambition (inspector panels,
  docking) that is out of scope.

## 3. The scene layer

The house pattern — plain's `project()`, the TUI's byte-deterministic paint —
continues: the GUI's core is a **pure function `compose(frame) -> Scene`**,
where `Scene` is frozen data naming everything the window will show:

- a cell grid (glyph, foreground/background color, grid position) for grid
  viewports, or text blocks for room/dialogue/menu/lock viewports;
- status region content (hp/mp, turn, mode, area);
- the scrolling log's visible lines;
- the advertised input affordances (drawn key hints, and — from slice 13C —
  click targets, §4).

Everything downstream of `compose` is a thin `paint(scene, surface)` that blits
cells and text; only `paint` and the event pump import pygame. The split is the
load-bearing verification decision: **the Scene is the evidence, the pixels are
derived material** — the same relationship frames have to ANSI output in `0003`
§11. Scene goldens and projection-consistency tests run without SDL present;
pixel output is covered by a small smoke layer (§5).

`compose` lives beside the other frontends (`frontends/gui/`), imports only
`glyphwright.api` and the frame types, and must itself stay importable without
pygame installed.

## 4. Input mapping

ADR-003 holds: keys and clicks exist only in this frontend; the kernel sees
semantic commands.

- **Keyboard.** The TUI's `translate(key, frame)` already maps normalized key
  names against the frame's grammar, is pure, and contains nothing
  terminal-specific. It moves to a shared frontend-internal module
  (`frontends/keymap.py`); the TUI and GUI both consume it, so the two
  interactive frontends cannot drift apart on bindings. The GUI's only new
  keyboard code normalizes pygame key events into the same key names the
  decoders in `tui/keys.py` produce.
- **Mouse (slice 13C).** Click handling resolves against the Scene, not the
  screen: every interactive scene element (an exit hint, a menu row, a
  dialogue choice) carries the semantic command it advertises, placed there by
  `compose` from the frame's `CommandGrammar`. A click finds the element under
  the cursor and sends its command. Because click targets are minted from the
  grammar at compose time, the mouse — like the keyboard — can never say
  something the grammar cannot, and click dispatch is testable headlessly as
  pure geometry over scene data.

## 5. Rendering and verification

**Glyphs first (ADR-007).** The default presentation draws the same ASCII
glyphs the terminal shows, in a monospaced font — the GUI is recognizably the
same game, and content packs need nothing new. A bitmap tileset sits behind a
flag (slice 13C): a pack-optional glyph→image table, with glyph rendering as
the universal fallback. Tilesets change `paint`, never `compose` — the Scene
still speaks glyphs, and the tileset is a paint-time skin, exactly parallel to
`0003` §12's Unicode-tileset flag.

**Font determinism.** Text is rasterized with pygame-ce's bundled font at a
fixed size, so `paint` has no system-font lookup and no environment-dependent
fallback. Cross-platform pixel identity is *not* promised — font rasterization
may differ by platform — which is precisely why pixel hashes are smoke
evidence, not primary evidence.

**Test taxonomy** (mirrors `0003` §17, strongest evidence first):

1. **Scene goldens** — reviewed `compose` output for representative frames,
   the GUI's analogue of plain-transcript goldens. Run without pygame.
2. **Projection consistency** — every fact plain's `project()` commits to
   paper (turn, mode, area, tiles, messages, hp/mp, and the per-view extras)
   appears in the Scene, asserted per view type; the same contract the TUI
   already honors against plain. Run without pygame.
3. **Determinism** — equal frames compose equal Scenes; scene composition
   reads nothing but the frame.
4. **Headless paint smoke** (marked `e2e`, requires `[gui]`) — under
   `SDL_VIDEODRIVER=dummy`, `paint` renders every golden Scene without error,
   and a pixel hash per Scene is asserted *per platform-and-version pin* to
   catch unreviewed paint changes; the hash baseline is expected to move with
   pygame-ce upgrades and is blessed only by humans, like every golden.
5. **Keyboard/mouse dispatch** — pure tests over `translate` (already
   covered) and click-target resolution.

An interactive session cannot run under CI at all; like the TUI's real
keyboard reader, the event-pump loop is the one uncovered sliver, kept to a
minimal shell around tested parts.

## 6. Packaging, CLI, CI

- **`pyproject.toml`**: `[project.optional-dependencies] gui = ["pygame-ce>=2.5"]`.
  Core `dependencies` stays `[]`.
- **CLI**: `--frontend gui` joins the choices. Selecting it without the extra
  installed exits with a one-line install hint (`pip install "glyphwright[gui]"`);
  the pygame import is lazy inside the gui session module, so every other
  frontend is untouched by the extra's absence.
- **CI**: the existing quality matrix installs the extra and sets
  `SDL_VIDEODRIVER=dummy` so the full suite, including paint smoke, runs on
  both OSes. A **bare job** runs the core suite *without* the extra — proving
  continuously that the package and every non-GUI test work with pygame absent,
  the same mechanical enforcement pattern §16.1 uses for TermVerify absence.
  The package job additionally smoke-imports the built wheel without the
  extra, unchanged.
- **TermVerify boundary**: unaffected. The GUI is not a PTY program; the
  three adapter flavors (`0003` §16.3) keep targeting plain/JSONL/TUI. The
  GUI's verification story is the in-repo taxonomy above.

## 7. Implementation slices

Following the 9A/9B precedent, one design, three slices; each lands with its
tests and docs, and later slices may be re-scoped by what earlier ones learn.

- **13A — Exploration GUI (walking skeleton).** `frontends/gui/` with
  `compose`/`paint`/event pump; grid and room viewports, status region, log;
  keyboard input via the shared keymap; `--frontend gui`; the `[gui]` extra,
  lazy import, bare CI job, dummy-driver smoke tests; scene goldens and
  projection consistency for the covered views. Battle/dialogue/lock frames
  render as an honest placeholder naming the mode and directing to the
  terminal frontends — never a crash.
- **13B — Full parity.** Menu battle, dialogue, and lock views; the GUI plays
  everything the TUI plays; projection consistency extended to all view
  types. This is the slice that completes the usability claim.
- **13C — Tileset and mouse.** The tileset flag with pack-optional glyph→image
  tables and glyph fallback; click targets in the Scene and mouse dispatch.
  Nice-to-haves beyond this (animation, sound, resizable layouts) are out of
  scope for this document and would be a new design.

## 8. Open questions

1. **Pixel-hash portability** — whether per-platform hashes are stable enough
   across runner images to be worth keeping, or whether "paints without
   error" suffices as smoke. Decide during 13A with real CI evidence.
   *13A interim (2026-07-18):* shipped with paints-without-error plus
   within-process determinism (same scene twice ⇒ identical buffer bytes)
   and no committed hash baselines; revisit once the matrix has produced
   evidence either way.
2. **Window geometry** — 13A ships a fixed-size window derived from the
   TUI's region budgets; whether resizing is wanted (and what it means for
   scene goldens) is deferred until a person asks for it.
