"""The `ue5` extra must stay isolated from the core (design 0012 §9).

The UE5 host is the one component that is not offline/pinnable, so it lives
behind its own extra exactly like the GUI (`0011` §6): the bare CI job syncs
without `--all-extras`, and the core package must import cleanly with `mcp`
absent. This test proves the core never imports the `ue5` package — a stray
top-level import would pass a normal local run and break the bare job, the
same failure mode the GUI bare check guards against.
"""

from __future__ import annotations

import subprocess
import sys


def test_core_imports_without_touching_the_ue5_package() -> None:
    # Import the whole core surface, then assert neither the ue5 package nor
    # its `mcp` dependency entered the process. Run in a subprocess so the
    # suite's own imports cannot pollute the check.
    code = (
        "import sys\n"
        "import glyphwright, glyphwright.cli, glyphwright.api\n"
        "import glyphwright.frontends.presentation.scenegraph\n"
        "import glyphwright.frontends.presentation.manifest\n"
        "import glyphwright.frontends.presentation.clickmove\n"
        "bad = [m for m in sys.modules if m == 'mcp' or m.startswith('mcp.') "
        "or '.ue5' in m or m.endswith('.ue5')]\n"
        "sys.exit(1 if bad else 0)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, (
        f"core pulled in the ue5 package: {result.stdout}{result.stderr}"
    )


def test_ue5_package_reports_mcp_absent_cleanly() -> None:
    # With the extra installed the import works; this just pins that the
    # package is importable under the extra so the e2e can exercise it.
    import importlib.util

    if importlib.util.find_spec("mcp") is None:
        import pytest

        pytest.skip("ue5 extra not installed (bare suite)")
    import glyphwright.frontends.presentation.ue5.client as client

    assert hasattr(client, "UE5Client")
