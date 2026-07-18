"""The UE5 presentation host: an isolated MCP client (design 0012 §9, 14C).

This package is the *only* component of GlyphWright that is not offline and
pinnable: it talks to a running Unreal Editor over MCP. It therefore lives
behind the ``ue5`` extra, is excluded from the bare CI job like the GUI
(`0011` §6), and is never imported by the core — the same mechanical-isolation
pattern ADR-001 uses for TermVerify.

The source of truth for navigation and game state stays in GlyphWright packs;
this host *realizes* a :class:`~glyphwright.frontends.presentation.scenegraph.SceneGraph`
into level geometry and reports pixel evidence back. It never decides game
rules.
"""
