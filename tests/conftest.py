"""Test configuration shared by every test module.

In CI, Hypothesis runs derandomized, so a failure there reproduces exactly on
any machine (v0 finding T8). Locally it keeps exploring new examples.
"""

from __future__ import annotations

import os

from hypothesis import settings

settings.register_profile("ci", derandomize=True, print_blob=True)
if os.environ.get("CI"):
    settings.load_profile("ci")
