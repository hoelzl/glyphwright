"""The enforcing tests for the invariants in ``AGENTS.md``.

Each test names the invariant it holds. Determinism is enforced by
``test_determinism.py`` and semantic evidence by ``test_wire.py``.
"""

from __future__ import annotations

import ast
import io
import json
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator

from glyphwright.api import Engine, decode_command, reference_pack
from glyphwright.frontends import jsonl, plain
from glyphwright.harness.schema import all_schemas

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "glyphwright"
CORE = ("kernel", "world", "modes", "frames", "content")

# Modules that reach the terminal, the clock, the filesystem, the network, or
# ambient entropy. The core imports none of them.
_AMBIENT_MODULES = frozenset(
    {
        "asyncio",
        "datetime",
        "importlib",
        "io",
        "os",
        "pathlib",
        "random",
        "secrets",
        "shutil",
        "socket",
        "subprocess",
        "sys",
        "tempfile",
        "time",
        "urllib",
        "uuid",
    }
)
_AMBIENT_CALLS = frozenset({"open", "print", "input"})


def _core_modules() -> list[Path]:
    return sorted(path for part in CORE for path in (PACKAGE / part).rglob("*.py"))


def test_the_core_does_no_ambient_io() -> None:
    """Invariant: no ambient I/O in the core."""
    offences = []
    for path in _core_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.split(".")[0] in _AMBIENT_MODULES:
                    line = getattr(node, "lineno", 0)
                    offences.append(f"{path.name}:{line} imports {name}")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in _AMBIENT_CALLS
            ):
                offences.append(f"{path.name}:{node.lineno} calls {node.func.id}()")
    assert not offences, offences


def test_the_core_module_list_is_not_empty() -> None:
    assert len(_core_modules()) >= 10


_VALIDATORS = {
    schema["$id"]: Draft202012Validator(schema) for schema in all_schemas().values()
}


@settings(max_examples=100, deadline=None)
@given(lines=st.lists(st.text(max_size=30), max_size=8))
def test_arbitrary_input_never_raises_and_always_yields_valid_json(
    lines: list[str],
) -> None:
    """Invariant: invalid input is a value, never an exception."""
    script = "".join(line.replace("\n", " ") + "\n" for line in lines)
    for harness in (False, True):
        output = io.StringIO()
        engine = Engine.new(reference_pack(), seed=1)
        assert (
            jsonl.run_session(engine, io.StringIO(script), output, harness=harness) == 0
        )
        for emitted in output.getvalue().splitlines():
            payload = json.loads(emitted)
            _VALIDATORS[payload["schema"]].validate(payload)


@settings(max_examples=100, deadline=None)
@given(lines=st.lists(st.text(max_size=30), max_size=8))
def test_the_plain_frontend_never_raises(lines: list[str]) -> None:
    """Invariant: invalid input is a value, never an exception."""
    script = "".join(line.replace("\n", " ") + "\n" for line in lines)
    engine = Engine.new(reference_pack(), seed=1)
    assert plain.run_session(engine, io.StringIO(script), io.StringIO()) == 0


@settings(max_examples=200, deadline=None)
@given(text=st.text(max_size=40))
def test_any_decoded_command_steps_without_raising(text: str) -> None:
    """Invariant: invalid input is a value, never an exception."""
    command = decode_command(text)
    if command is not None:
        result = Engine.new(reference_pack(), seed=1).step(command)
        assert result.accepted or result.rejection is not None


def test_only_the_api_is_the_public_surface() -> None:
    """Invariant: one public surface. Frontends import the engine via the API."""
    for name in ("plain.py", "jsonl.py"):
        tree = ast.parse((PACKAGE / "frontends" / name).read_text(encoding="utf-8"))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert "glyphwright.api" in imported
        assert not any(
            module.startswith("glyphwright.kernel.step") for module in imported
        )
