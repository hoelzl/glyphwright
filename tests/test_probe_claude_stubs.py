from collections.abc import Sequence
from pathlib import Path

import docs_tool
import probe_claude_stubs as probe
import pytest


def fake_runner(*, expand: bool, auto: bool) -> probe.Runner:
    """Answer like Claude would if the stub did (or did not) deliver the skill."""

    def runner(command: Sequence[str], cwd: Path) -> str:
        skill = cwd / docs_tool.SKILLS_DIR / probe.SKILL_NAME / "SKILL.md"
        token = skill.read_text(encoding="utf-8").rsplit(" ", 1)[-1].strip()
        stub = (cwd / ".claude/commands/stub-probe.md").read_text(encoding="utf-8")
        delivered = token in stub or "@.agents/skills/stub-probe/SKILL.md" in stub
        is_slash = command[2].startswith("/")
        ok = delivered and (expand if is_slash else auto)
        return f"{token}\n" if ok else "I don't know the token.\n"

    return runner


def test_probe_passes_when_the_stub_delivers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert probe.main([], runner=fake_runner(expand=True, auto=False)) == 0
    out = capsys.readouterr().out
    assert "expansion: pass" in out
    assert "automatic use: FAIL (reported only)" in out


def test_probe_fails_when_expansion_fails() -> None:
    assert probe.main([], runner=fake_runner(expand=False, auto=True)) == 1


def test_probe_isolates_tools_and_settings() -> None:
    (_, expansion), (_, automatic) = probe.probes("claude")
    assert expansion[expansion.index("--tools") + 1] == ""
    assert automatic[automatic.index("--tools") + 1] == "Skill"
    assert "--strict-mcp-config" in expansion
    assert expansion[expansion.index("--setting-sources") + 1] == "project"


def test_inline_mode_puts_the_token_in_the_stub(tmp_path: Path) -> None:
    probe.make_repo(tmp_path, "probe-abc", "inline")
    stub = (tmp_path / ".claude/commands/stub-probe.md").read_text(encoding="utf-8")
    assert "probe-abc" in stub
