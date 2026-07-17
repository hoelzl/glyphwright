import importlib.metadata

import glyphwright


def test_package_version_matches_installed_metadata() -> None:
    assert glyphwright.__version__ == importlib.metadata.version("glyphwright")
