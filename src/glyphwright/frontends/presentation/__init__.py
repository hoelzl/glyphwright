"""The presentation seam: what a human-facing frontend is made of (design 0012).

This package holds the presentation-only machinery that sits *between* the
engine's semantic frames and any rendering substrate — the pathfinder click-
to-move compiles through (§6), the presentation manifest (§5), and the
``compose(frame, manifest) -> SceneGraph`` core (§3). Nothing here imports a
rendering substrate, reads a wall clock, or touches the kernel's command
semantics: presentation convenience always compiles down to the existing
command grammar.
"""
