"""The CLI's gui wiring that must work with the extra absent (0011 §6)."""

from __future__ import annotations

import sys

import pytest

from glyphwright import cli


def test_a_missing_gui_extra_fails_with_an_install_hint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A None entry makes ``import pygame`` raise ImportError even when the
    # extra is installed, which is exactly the absent-extra experience.
    monkeypatch.setitem(sys.modules, "pygame", None)
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--frontend", "gui"])
    assert excinfo.value.code == 2
    assert 'pip install "glyphwright[gui]"' in capsys.readouterr().err
