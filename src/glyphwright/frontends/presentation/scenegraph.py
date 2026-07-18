"""The SceneGraph: the presentation's evidence (design 0012 §3).

``compose(frame, manifest) -> SceneGraph`` is the presentation core, the same
relationship to a renderer that frames have to ANSI output in `0003` §11: the
SceneGraph is the evidence, the realized scene is derived material. It is
frozen, pygame-free, and engine-free data naming everything a substrate will
draw — ordered placements with their compositing tier, a camera, the
transition descriptors a painter may interpolate, and the input affordances
minted from the grammar. Goldens and projection-consistency run with no
renderer installed; only ``realize`` and the event pump import a substrate.
"""

from __future__ import annotations

from dataclasses import dataclass

from glyphwright.frames.frame import GridView, SemanticFrame
from glyphwright.frontends.presentation.manifest import PresentationManifest
from glyphwright.kernel.events import Event, Moved

#: Compositing tiers (0012 §4): the painterly stacking at one position. A cell
#: has tiers; tier is decided here at compose time, never re-derived downstream.
Tier = str
GROUND: Tier = "ground"
FIXTURE: Tier = "fixture"
ACTOR: Tier = "actor"


@dataclass(frozen=True, slots=True)
class Placement:
    """One drawable thing: what, where semantically, where on screen, which tier.

    ``semantic_pos`` is the world's own identifier (``area:x,y``); ``render_pos``
    is the substrate-space ``(x, y, z)`` the painter places it at, with z-level
    riding here rather than in the tier (0012 §4). ``asset_id`` is the manifest's
    binding for the glyph when one exists, else the glyph itself.
    """

    glyph: str
    semantic_pos: str
    render_pos: tuple[int, int, int]
    asset_id: str
    tier: Tier


@dataclass(frozen=True, slots=True)
class Camera:
    """A deterministic function of the viewport and frame, not of wall-clock input.

    ``origin`` is the viewport's top-left in world coordinates; ``focus`` is the
    position the camera should center on (the player when present). Both derive
    from the frame alone, so equal frames frame identically (0012 §7).
    """

    origin: tuple[int, int]
    focus: tuple[int, int] | None


@dataclass(frozen=True, slots=True)
class Transition:
    """A cosmetic animation directive for one event in the frame's log delta.

    A painter may interpolate between the prior and current SceneGraph using
    these; they carry no semantic weight and are never gated on finishing —
    input is accepted at frame boundaries (0012 §6). ``kind`` is one of
    ``move`` / ``strike`` / ``spawn`` / ``despawn``.
    """

    kind: str
    glyph: str
    from_pos: str | None
    to_pos: str | None


@dataclass(frozen=True, slots=True)
class SceneGraph:
    """Everything a presentation will realize, as frozen data.

    Equal frames and equal manifests compose equal SceneGraphs — the property
    the determinism tests assert. ``manifest_hash`` is carried so a realized
    scene can be traced to the exact presentation content that produced it
    (0012 §5): same seed, different manifest is detectably different.
    """

    placements: tuple[Placement, ...]
    camera: Camera
    transitions: tuple[Transition, ...]
    affordances: tuple[str, ...]
    manifest_hash: str


def compose(
    frame: SemanticFrame,
    manifest: PresentationManifest,
    *,
    events: tuple[Event, ...] = (),
) -> SceneGraph:
    """Compose the presentation core from a frame and a manifest.

    Pure: same frame, same manifest, same events, same SceneGraph. Reads
    nothing but its inputs — no clock, no substrate, no kernel internals.
    """
    placements: list[Placement] = []
    camera = Camera(origin=(0, 0), focus=None)
    if isinstance(frame.viewport, GridView):
        viewport = frame.viewport
        placements = _grid_placements(viewport, manifest)
        camera = _camera(viewport, frame)
    transitions = _transitions(events, placements)
    return SceneGraph(
        placements=tuple(placements),
        camera=camera,
        transitions=transitions,
        affordances=frame.commands.verb_names(),
        manifest_hash=manifest.hash,
    )


def _grid_placements(
    viewport: GridView, manifest: PresentationManifest
) -> list[Placement]:
    """Ordered placements: every ground, then every fixture, then every actor.

    Ordering is by tier first (ground under fixture under actor), then by
    reading order within a tier, so the painter draws the stack correctly by
    iterating once. Semantic positions reconstruct from the viewport origin
    plus the cell offset.
    """
    placements: list[Placement] = []
    ox, oy = viewport.origin
    for tier_index, tier in enumerate((GROUND, FIXTURE, ACTOR)):
        for y, row in enumerate(viewport.cells):
            for x, cell in enumerate(row):
                glyph = (cell.ground, cell.fixture, cell.actor)[tier_index]
                if glyph is None or glyph == " ":
                    continue
                placements.append(
                    Placement(
                        glyph=glyph,
                        semantic_pos=f"{viewport.area}:{ox + x},{oy + y}",
                        render_pos=(x, y, 0),
                        asset_id=manifest.bindings.get(glyph, glyph),
                        tier=tier,
                    )
                )
    return placements


def _camera(viewport: GridView, frame: SemanticFrame) -> Camera:
    player = next((actor for actor in frame.actors if actor.id == "player"), None)
    focus = None
    if player is not None and player.at.area == viewport.area:
        x_text, _, y_text = player.at.local.partition(",")
        focus = (int(x_text) - viewport.origin[0], int(y_text) - viewport.origin[1])
    return Camera(origin=viewport.origin, focus=focus)


def _transitions(
    events: tuple[Event, ...], placements: list[Placement]
) -> tuple[Transition, ...]:
    out: list[Transition] = []
    for event in events:
        if isinstance(event, Moved):
            out.append(
                Transition(
                    kind="move",
                    glyph=_glyph_of(event.actor, event.destination, placements),
                    from_pos=str(event.origin),
                    to_pos=str(event.destination),
                )
            )
    return tuple(out)


def _glyph_of(entity_id: str, destination: object, placements: list[Placement]) -> str:
    """The renderable glyph an actor id maps to, for a cosmetic transition.

    The event names the actor by id; the painter needs the glyph to tween.
    Resolved from the actor-tier placement now standing at the destination —
    the entity the frame shows there. Falls back to the id itself when no such
    placement exists (a move off-screen), so the directive is never unusable.
    """
    dest = str(destination)
    for placement in placements:
        if placement.tier == ACTOR and placement.semantic_pos == dest:
            return placement.glyph
    return entity_id


def scenegraph_text(graph: SceneGraph) -> str:
    """A stable text serialization of a SceneGraph, for reviewed goldens.

    Placements are grouped by tier and re-joined into glyph rows so the dump
    reads like a layered map; a human reviews it the way they review a plain
    transcript. The camera, transitions, affordances, and manifest hash follow
    so a golden change surfaces any of them moving.
    """
    lines = [f"== scenegraph · manifest {graph.manifest_hash[:19]}… =="]
    if graph.placements:
        width = max(p.render_pos[0] for p in graph.placements) + 1
        height = max(p.render_pos[1] for p in graph.placements) + 1
        for tier in (GROUND, FIXTURE, ACTOR):
            rows = [[" "] * width for _ in range(height)]
            present = False
            for placement in graph.placements:
                if placement.tier != tier:
                    continue
                present = True
                x, y, _ = placement.render_pos
                rows[y][x] = placement.glyph
            if present:
                lines.append(f"-- {tier} --")
                lines.extend("".join(row).rstrip() for row in rows)
    focus = graph.camera.focus
    lines.append(f"camera origin={graph.camera.origin} focus={focus if focus else '-'}")
    for transition in graph.transitions:
        lines.append(
            f"transition {transition.kind} {transition.glyph} "
            f"{transition.from_pos}->{transition.to_pos}"
        )
    if graph.affordances:
        lines.append("affordances: " + ", ".join(graph.affordances))
    return "\n".join(lines)
