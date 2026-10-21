import glyphwright


def test_version_comes_from_the_package_metadata() -> None:
    assert glyphwright.__version__ == "0.1.0.dev0"
