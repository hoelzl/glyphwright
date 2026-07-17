"""The full-screen terminal frontend: hand-rolled ANSI region painting.

Chosen over a TUI framework (0003 §20.1) because the engine is turn-based: a
blocking key -> step -> repaint loop needs no async runtime, and the whole
screen is a pure, byte-deterministic function of the frame — which is exactly
what makes PTY evidence reviewable. Keystrokes translate into the same command
language every frontend speaks (ADR-003); nothing else differs.
"""
