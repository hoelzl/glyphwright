from pathlib import Path

import docs_tool
import pytest

AGENTS = "# Agent guide\n\nThe map for agents.\n"


def write(root: Path, path: str, text: str) -> Path:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")
    return target


def index(title: str) -> str:
    return (
        f"# {title}\n\nWhat this folder holds.\n\n"
        f"{docs_tool.INDEX_BEGIN}\n{docs_tool.INDEX_END}\n"
    )


#: The planned paths the tests rely on, independent of the repository's own.
TEST_PLANNED = {
    ".agents/skills/": "created by a test",
    ".claude/commands/": "created by a test",
    "docs/knowledge/": "created by a test",
}


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(docs_tool, "PLANNED", TEST_PLANNED)
    write(tmp_path, "AGENTS.md", AGENTS)
    write(tmp_path, "docs/README.md", index("Documentation map"))
    write(tmp_path, "docs/guide.md", "# Guide\n\nHow to do things.\n")
    write(tmp_path, "docs/plans/README.md", index("Plans"))
    write(tmp_path, "docs/plans/active/s1.md", "# S1\n\nThe first slice.\n")
    docs_tool.build(tmp_path)
    return tmp_path


def rules(problems: list[docs_tool.Problem]) -> list[str]:
    return [problem.rule for problem in problems]


def test_a_built_repository_passes(repo: Path) -> None:
    assert docs_tool.check(repo) == []


def test_index_lists_each_page_in_the_nearest_readme(repo: Path) -> None:
    top = docs_tool.read(repo / "docs/README.md")
    plans = docs_tool.read(repo / "docs/plans/README.md")
    assert "- [Guide](guide.md): How to do things." in top
    assert "- [plans/: Plans](plans/README.md): What this folder holds." in top
    assert "s1.md" not in top
    assert "- [S1](active/s1.md): The first slice." in plans


def test_a_new_page_makes_the_index_stale(repo: Path) -> None:
    write(repo, "docs/other.md", "# Other\n\nSomething else.\n")
    assert rules(docs_tool.check(repo)) == ["generated views match a fresh generation"]
    docs_tool.build(repo)
    assert docs_tool.check(repo) == []


def test_agents_md_over_budget_fails(repo: Path) -> None:
    over = AGENTS + "\n" + "- line\n" * docs_tool.AGENTS_MD_MAX_LINES
    write(repo, "AGENTS.md", over)
    assert "AGENTS.md stays within its size budget" in rules(docs_tool.check(repo))


@pytest.mark.parametrize(
    "path", ["CLAUDE.md", ".github/copilot-instructions.md", ".claude/skills/x.md"]
)
def test_second_instruction_or_skills_location_fails(repo: Path, path: str) -> None:
    write(repo, path, "# Copy\n\nA copy of the instructions.\n")
    assert any(
        "only" in rule or "stops reading" in rule
        for rule in rules(docs_tool.check(repo))
    )


def test_the_fallback_claude_md_is_allowed(repo: Path) -> None:
    write(repo, "CLAUDE.md", "@AGENTS.md\n")
    problems = docs_tool.check_instruction_files(repo)
    assert problems == []


def test_broken_link_and_missing_path_fail(repo: Path) -> None:
    write(
        repo,
        "docs/guide.md",
        "# Guide\n\nHow to do things.\n\nSee [x](missing.md) and `src/nowhere.py`.\n",
    )
    messages = [problem.message for problem in docs_tool.check(repo)]
    assert "broken link missing.md" in messages
    assert "missing path `src/nowhere.py`" in messages


def test_link_anchor_must_exist(repo: Path) -> None:
    write(
        repo,
        "docs/guide.md",
        "# Guide\n\nHow to do things.\n\n## Steps\n\n[a](#steps) [b](#nope)\n",
    )
    messages = [problem.message for problem in docs_tool.check(repo)]
    assert messages == ["missing anchor #nope"]


def test_planned_path_passes_until_it_exists(repo: Path) -> None:
    write(repo, "docs/guide.md", "# Guide\n\nHow to do things in `docs/knowledge/`.\n")
    docs_tool.build(repo)
    assert docs_tool.check(repo) == []
    write(repo, "docs/knowledge/README.md", index("Knowledge"))
    docs_tool.build(repo)
    assert "PLANNED holds only paths that do not exist yet" in rules(
        docs_tool.check(repo)
    )


def test_page_without_purpose_fails(repo: Path) -> None:
    write(repo, "docs/guide.md", "# Guide\n\n- just a list\n")
    docs_tool.build(repo)
    assert rules(docs_tool.check(repo)) == [
        "every doc opens with its purpose: what it covers, when to read it"
    ]


def test_long_page_needs_contents(repo: Path) -> None:
    body = "# Long\n\nA long page.\n\n## Part\n\n" + "text\n" * 100
    write(repo, "docs/guide.md", body)
    docs_tool.build(repo)
    assert len(docs_tool.check(repo)) == 1
    write(repo, "docs/guide.md", body.replace("## Part", "## Contents\n\n## Part"))
    assert docs_tool.check(repo) == []


def test_plan_outside_active_or_completed_fails(repo: Path) -> None:
    write(repo, "docs/plans/s2.md", "# S2\n\nThe second slice.\n")
    docs_tool.build(repo)
    assert rules(docs_tool.check(repo)) == [
        "a plan's folder says whether it is current"
    ]


SKILL = (
    "---\nname: play-a-session\n"
    "description: Plays a session. Use when asked to play: the game.\n---\n"
    "# Play a session\n\nSteps.\n"
)


def test_skill_gets_a_generated_stub(repo: Path) -> None:
    write(repo, ".agents/skills/play-a-session/SKILL.md", SKILL)
    assert "generated views match a fresh generation" in rules(docs_tool.check(repo))
    docs_tool.build(repo)
    stub = docs_tool.read(repo / ".claude/commands/play-a-session.md")
    assert stub.startswith(
        '---\ndescription: "Plays a session. Use when asked to play: the game."\n---\n'
    )
    assert "@.agents/skills/play-a-session/SKILL.md\n\n$ARGUMENTS\n" in stub
    problems = docs_tool.check(repo)
    assert [p.message for p in problems] == [
        "PLANNED lists `.agents/skills/`, which now exists",
        "PLANNED lists `.claude/commands/`, which now exists",
    ]


def test_stub_without_skill_is_removed_by_build(repo: Path) -> None:
    write(repo, ".claude/commands/orphan.md", "anything\n")
    assert "generated views match a fresh generation" in rules(docs_tool.check(repo))
    docs_tool.build(repo)
    assert not (repo / ".claude/commands/orphan.md").exists()


def test_skill_name_must_match_folder(repo: Path) -> None:
    write(repo, ".agents/skills/other/SKILL.md", SKILL)
    docs_tool.build(repo)
    messages = [p.message for p in docs_tool.check_skills(repo)]
    assert messages == ["name 'play-a-session' is invalid or differs from the folder"]


def test_main_reports_rule_and_fix(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(repo, "docs/other.md", "# Other\n\nSomething else.\n")
    assert docs_tool.main(["check"], root=repo) == 1
    out = capsys.readouterr().out
    assert "docs/README.md: generated index is stale" in out
    assert "  rule: generated views match a fresh generation" in out
    assert f"  fix:  run `{docs_tool.BUILD_COMMAND}`" in out


def test_inline_mode_copies_the_body_and_relinks(repo: Path) -> None:
    body = "# Play\n\nSee [the map](references/map.md) and [docs](https://x.org).\n"
    stub = docs_tool.render_stub("play", "Plays.", body, "inline")
    assert "@.agents/skills" not in stub
    assert "This skill's files are in `.agents/skills/play/`." in stub
    assert "[the map](../../.agents/skills/play/references/map.md)" in stub
    assert "[docs](https://x.org)" in stub
    assert stub.endswith("\n\n$ARGUMENTS\n")


def test_inline_stub_links_resolve(repo: Path) -> None:
    skill = SKILL.replace("Steps.", "Steps in [the guide](guide.md).")
    write(repo, ".agents/skills/play-a-session/SKILL.md", skill)
    write(repo, ".agents/skills/play-a-session/guide.md", "# Guide\n\nThe guide.\n")
    stubs = docs_tool.expected_stubs(repo, "inline")
    for path, content in stubs.items():
        write(repo, path, content)
    stub = repo / ".claude/commands/play-a-session.md"
    assert docs_tool.check_references(repo, stub) == []


def test_unknown_stub_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown stub mode"):
        docs_tool.render_stub("x", "X.", "", "copy")


def test_an_empty_planned_folder_still_counts_as_planned(repo: Path) -> None:
    (repo / "docs/knowledge").mkdir()
    assert docs_tool.check_planned(repo) == []


def test_a_versioned_schema_tag_in_a_current_page_fails(repo: Path) -> None:
    write(
        repo,
        "docs/wire.md",
        "# Wire\n\nWhat the stream says.\n\nA `glyphwright.frame/3` line.\n",
    )
    docs_tool.build(repo)
    assert rules(docs_tool.check(repo)) == ["no volatile facts in prose"]


def test_dated_records_may_name_versions(repo: Path) -> None:
    write(
        repo,
        "docs/decisions/0009-x.md",
        "# 0009 - X\n\nWhy X. Read it when Y.\n\nWe moved to `glyphwright.frame/3`.\n",
    )
    docs_tool.build(repo)
    assert "no volatile facts in prose" not in rules(docs_tool.check(repo))


RECORD = (
    "# 0001 - X\n\nWhy X. Read it when Y.\n\n"
    "## Context\n\nY happened, and Z.\n\n"
    "## Decision\n\nDo X.\n\n"
    "## Consequences\n\nX costs W.\n"
)
DECISION_RULE = "a decision record changes only with a logged revision"


@pytest.fixture
def sealed(repo: Path) -> Path:
    write(repo, "docs/decisions/0001-x.md", RECORD)
    docs_tool.build(repo)
    assert docs_tool.check(repo) == []
    return repo


def revise(root: Path, old: str, new: str, entry: str | None = None) -> None:
    path = root / "docs/decisions/0001-x.md"
    text = docs_tool.read(path).replace(old, new)
    if entry is not None:
        text += f"\n## Revisions\n\n{entry}\n"
    write(root, "docs/decisions/0001-x.md", text)
    docs_tool.build(root)


def test_an_edit_without_a_revision_entry_fails_and_is_not_resealed(
    sealed: Path,
) -> None:
    revise(sealed, "Y happened, and Z.", "Y happened.")
    problems = docs_tool.check(sealed)
    assert rules(problems) == [DECISION_RULE]
    assert "without a revision entry" in problems[0].message
    assert "supersedes" in problems[0].fix


def test_an_erratum_with_a_dated_entry_is_resealed(sealed: Path) -> None:
    entry = '- **2026-10-23**, Context: was "Y happened, and Z."; Z did not.'
    revise(sealed, "Y happened, and Z.", "Y happened.", entry)
    assert docs_tool.check(sealed) == []


def test_an_entry_must_open_with_its_date_and_section(sealed: Path) -> None:
    revise(sealed, "Y happened, and Z.", "Y happened.", "- dropped Z")
    assert "does not open with its date" in docs_tool.check(sealed)[0].message


def test_changing_the_decision_needs_a_superseding_record(sealed: Path) -> None:
    entry = '- **2026-10-23**, Context: was "Do X."; we do V now.'
    revise(sealed, "Do X.", "Do V.", entry)
    problems = docs_tool.check(sealed)
    assert [problem.message for problem in problems] == ["the Decision section changed"]


def test_an_entry_naming_the_decision_lets_a_wording_fix_through(
    sealed: Path,
) -> None:
    entry = '- **2026-10-23**, Decision: was "Do X."; a typo, same meaning.'
    revise(sealed, "Do X.", "Do X!", entry)
    assert docs_tool.check(sealed) == []


def test_revision_entries_are_never_removed(sealed: Path) -> None:
    entry = '- **2026-10-23**, Context: was "Y happened, and Z."; Z did not.'
    revise(sealed, "Y happened, and Z.", "Y happened.", entry)
    revise(sealed, f"\n## Revisions\n\n{entry}\n", "")
    assert "revision entry was removed" in docs_tool.check(sealed)[0].message


def test_a_sealed_record_cannot_be_deleted(sealed: Path) -> None:
    (sealed / "docs/decisions/0001-x.md").unlink()
    docs_tool.build(sealed)
    assert rules(docs_tool.check(sealed)) == [
        "decision records are superseded, not deleted"
    ]


def test_a_new_record_without_a_seal_is_stale(sealed: Path) -> None:
    write(sealed, "docs/decisions/0002-y.md", RECORD.replace("0001", "0002"))
    seals = docs_tool.read(sealed / docs_tool.SEALS)
    docs_tool.build(sealed)
    write(sealed, docs_tool.SEALS, seals)
    assert [problem.message for problem in docs_tool.check(sealed)] == [
        "stale decision seals"
    ]
