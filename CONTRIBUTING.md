# Contributing to GlyphWright

Use `uv`; do not install project dependencies with `pip` or edit `uv.lock` manually. Python 3.12 is the minimum supported version; CI continuously tests 3.12 through 3.14 without promising unlisted future versions.

Read [`docs/agent/design/0003-glyphwright-design.md`](docs/agent/design/0003-glyphwright-design.md) before proposing a non-trivial change; it is the authoritative design document and overrides any other document here.

Behavioral changes follow strict TDD. Start with the narrowest semantic test, verify the expected failure, implement the minimum, then add terminal-facing coverage only where the shipped interface changes. Core tests must not depend on ambient time, entropy, locale, filesystem, network, or terminal dimensions. Randomness itself is permitted and expected, but only through the injected seeded stream whose cursor is part of world state — never through module-level `random` or an unseeded generator.

Engine code must never import `termverify`, and the core test suite must pass with TermVerify not installed. Whether adapter and differential tests live here behind an optional dev-only extra, or in TermVerify's examples, is an open question to be settled when the adapter is built.

Before proposing a change, run:

```bash
uv --no-config sync --all-groups --locked
uv --no-config run pytest --cov --cov-report=term-missing
uv --no-config run ruff check .
uv --no-config run ruff format --check .
uv --no-config run mypy src tests
uv --no-config run pre-commit run --all-files
uv --no-config run pre-commit run --hook-stage pre-push --all-files
uv --no-config build
```

New dependencies, copied code, protocol changes, and baseline updates require explicit rationale. Agents may propose replay or golden changes, but a human-readable diff and human approval remain mandatory.
