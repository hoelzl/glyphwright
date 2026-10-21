#!/usr/bin/env python3
"""Build and check the documentation's derived views and structure rules.

Usage:
    uv run python scripts/docs_tool.py build   # rewrite the generated views
    uv run python scripts/docs_tool.py check   # fail on any rule violation

``build`` regenerates two kinds of derived view: the index block in every
``README.md`` under ``docs/``, and one Claude Code command stub per skill in
``.claude/commands/``. ``check`` writes nothing; it fails when a derived view
is stale or a documentation rule is broken, and every message names the rule
and the fix. The rules themselves are explained in ``CONTRIBUTING.md`` under
"Documentation rules"; this script is what enforces them.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

BUILD_COMMAND = "uv run python scripts/docs_tool.py build"

#: The size budget of the always-on instruction file, in lines.
AGENTS_MD_MAX_LINES = 100
#: Files longer than this must open with a "## Contents" section.
TOC_THRESHOLD_LINES = 100
#: A purpose paragraph longer than this is no longer a one-line summary.
PURPOSE_MAX_CHARS = 400
#: Agent Skills specification limits.
SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SKILL_NAME_MAX = 64
SKILL_DESCRIPTION_MAX = 1024
SKILL_BODY_MAX_LINES = 500
SKILL_FIELDS = frozenset(
    {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
)

SKILLS_DIR = ".agents/skills"
STUBS_DIR = ".claude/commands"
#: How a stub reaches its skill: "import" (an `@` import) or "inline" (a
#: copy of the body). Switch to "inline" when
#: `scripts/probe_claude_stubs.py` fails; see decision 0001.
STUB_MODE = "import"

#: Files whose presence would duplicate or shadow `AGENTS.md` or the skills.
FORBIDDEN = {
    ".claude/CLAUDE.md": "Claude Code stops reading AGENTS.md when it exists",
    "CLAUDE.local.md": "Claude Code stops reading AGENTS.md when it exists",
    ".github/copilot-instructions.md": "AGENTS.md is the only instruction file",
    ".claude/skills": f"{SKILLS_DIR}/ is the only skills folder",
    ".github/skills": f"{SKILLS_DIR}/ is the only skills folder",
}
#: The one permitted content of a fallback `CLAUDE.md`.
CLAUDE_MD_FALLBACK = "@AGENTS.md"

#: Paths that documents may name before they exist, each with its reason.
#: Remove an entry in the change that creates the path.
PLANNED: Mapping[str, str] = {
    ".claude/settings.json": "created once there are Claude-only settings",
}

#: Top-level directories a backticked repository path may start with.
REPO_ROOTS = (
    "src/",
    "tests/",
    "scripts/",
    "schemas/",
    "docs/",
    ".agents/",
    ".claude/",
    ".github/",
)
#: Dot-directories whose Markdown is checked.
VISIBLE_DOT_DIRECTORIES = frozenset({".agents", ".claude", ".github"})

INDEX_BEGIN = (
    "<!-- BEGIN GENERATED INDEX: edit the listed pages, not this list;"
    f" regenerate with `{BUILD_COMMAND}` -->"
)
INDEX_END = "<!-- END GENERATED INDEX -->"

_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(\s*(<[^>]+>|[^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
_DEFINITION = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(<[^>]+>|\S+)")
_CODE = re.compile(r"`([^`\n]+)`")
_EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//)", re.IGNORECASE)
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


@dataclass(frozen=True)
class Problem:
    """One rule violation, with the change that fixes it."""

    location: str
    message: str
    rule: str
    fix: str

    def render(self) -> str:
        return (
            f"{self.location}: {self.message}\n  rule: {self.rule}\n  fix:  {self.fix}"
        )


# --- reading Markdown -------------------------------------------------------


def read(path: Path) -> str:
    """Return *path* as text with newlines normalized to ``\\n``."""
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def split_frontmatter(text: str) -> tuple[dict[str, str] | None, str, int]:
    """Return ``(fields, body, body start line)`` for one-line YAML fields.

    ``fields`` is ``None`` when the text has no frontmatter at byte 0. Only
    ``key: value`` lines are understood; anything else raises ``ValueError``.
    """
    if not text.startswith("---\n"):
        return None, text, 1
    end = text.find("\n---\n", 3)
    if end == -1:
        raise ValueError("frontmatter is not closed by a '---' line")
    fields: dict[str, str] = {}
    for line in text[4:end].split("\n"):
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep or key != key.strip() or not key:
            raise ValueError(f"unsupported frontmatter line {line!r}")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = json.loads(value) if value[0] == '"' else value[1:-1]
        fields[key] = value
    body = text[end + 5 :]
    return fields, body, text[: end + 5].count("\n") + 1


def prose_lines(text: str) -> Iterator[tuple[int, str]]:
    """Yield ``(line number, line)`` outside frontmatter and code fences."""
    lines = text.split("\n")
    start = 0
    if lines and lines[0] == "---":
        for index in range(1, len(lines)):
            if lines[index] == "---":
                start = index + 1
                break
    in_fence = False
    for number, line in enumerate(lines[start:], start=start + 1):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield number, line


def title_and_purpose(text: str) -> tuple[str | None, str | None]:
    """Return the H1 on the first prose line and the paragraph after it."""
    lines = [line for _, line in prose_lines(text)]
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines or not lines[0].startswith("# "):
        return None, None
    title = lines[0][2:].strip()
    rest = lines[1:]
    while rest and not rest[0].strip():
        rest.pop(0)
    paragraph: list[str] = []
    for line in rest:
        if not line.strip():
            break
        paragraph.append(line.strip())
    if not paragraph or paragraph[0].startswith(("#", "-", "*", "|", ">", "<", "1.")):
        return title, None
    return title, " ".join(paragraph)


def slugify(heading: str) -> str:
    """Return the GitHub anchor slug of a heading's text."""
    text = heading.replace("`", "").replace("*", "")
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = unicodedata.normalize("NFKC", text).strip().lower()
    text = "".join(ch for ch in text if ch.isalnum() or ch in " -_")
    return text.replace(" ", "-")


def anchors(text: str) -> set[str]:
    """Return the heading anchors of a Markdown text."""
    seen: dict[str, int] = {}
    result: set[str] = set()
    for _, line in prose_lines(text):
        match = _HEADING.match(line)
        if match:
            slug = slugify(match.group(2))
            count = seen.get(slug, 0)
            seen[slug] = count + 1
            result.add(slug if count == 0 else f"{slug}-{count}")
    return result


def exists_exactly(path: Path) -> bool:
    """Return whether *path* exists with exactly this spelling of every part."""
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        try:
            names = os.listdir(current)
        except OSError:
            return False
        if part not in names:
            return False
        current = current / part
    return True


def markdown_files(root: Path) -> list[Path]:
    """Return the repository's Markdown files, sorted, skipping tool caches."""
    files: list[Path] = []
    for path in sorted(root.rglob("*.md")):
        parts = path.relative_to(root).parts
        hidden = [part for part in parts[:-1] if part.startswith(".")]
        if any(part not in VISIBLE_DOT_DIRECTORIES for part in hidden):
            continue
        if "node_modules" in parts:
            continue
        files.append(path)
    return files


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


# --- derived view 1: documentation indexes ----------------------------------


def nearest_index(root: Path, page: Path) -> Path | None:
    """Return the ``README.md`` that lists *page*: the nearest one above it."""
    docs = root / "docs"
    folder = page.parent.parent if page.name == "README.md" else page.parent
    while folder != docs.parent:
        candidate = folder / "README.md"
        if candidate.is_file() and candidate != page:
            return candidate
        if folder == docs:
            return None
        folder = folder.parent
    return None


def doc_pages(root: Path) -> list[Path]:
    docs = root / "docs"
    return sorted(docs.rglob("*.md")) if docs.is_dir() else []


def render_index(root: Path, index: Path) -> str:
    """Return the generated index block for the ``README.md`` at *index*."""
    entries: list[str] = []
    for page in doc_pages(root):
        if page == index or nearest_index(root, page) != index:
            continue
        title, purpose = title_and_purpose(read(page))
        link = page.relative_to(index.parent).as_posix()
        label = title or page.stem
        if page.name == "README.md":
            label = f"{page.parent.relative_to(index.parent).as_posix()}/: {label}"
        entries.append(f"- [{label}]({link}): {purpose or ''}".rstrip())
    return "\n".join([INDEX_BEGIN, *entries, INDEX_END])


def index_files(root: Path) -> list[Path]:
    return [page for page in doc_pages(root) if page.name == "README.md"]


def apply_index(text: str, block: str) -> str | None:
    """Return *text* with its generated block replaced, or ``None`` if absent."""
    start = text.find(INDEX_BEGIN)
    end = text.find(INDEX_END)
    if start == -1 or end == -1 or end < start:
        return None
    return text[:start] + block + text[end + len(INDEX_END) :]


# --- derived view 2: Claude Code command stubs ------------------------------


def skill_files(root: Path) -> list[Path]:
    skills = root / SKILLS_DIR
    return sorted(skills.glob("*/SKILL.md")) if skills.is_dir() else []


def _relink(body: str, name: str) -> str:
    """Rewrite the skill body's relative links to resolve from the stub."""
    prefix = f"../../{SKILLS_DIR}/{name}/"

    def fix(match: re.Match[str]) -> str:
        target = match.group(1)
        if _EXTERNAL.match(target) or target.startswith(("#", "<")):
            return match.group(0)
        return match.group(0).replace(f"({target}", f"({prefix}{target}", 1)

    return _LINK.sub(fix, body)


def render_stub(name: str, description: str, body: str, mode: str) -> str:
    """Return the Claude Code command stub for skill *name*.

    ``import`` mode loads the skill with an ``@`` import; ``inline`` mode
    copies the skill body, with its relative links rewritten.
    """
    source = f"{SKILLS_DIR}/{name}/SKILL.md"
    header = (
        "---\n"
        f"description: {json.dumps(description, ensure_ascii=False)}\n"
        "---\n"
        f"<!-- GENERATED from `{source}` by `{BUILD_COMMAND}`;"
        " edit the skill, not this stub -->\n"
    )
    if mode == "import":
        return f"{header}@{source}\n\n$ARGUMENTS\n"
    if mode == "inline":
        files = f"This skill's files are in `{SKILLS_DIR}/{name}/`.\n\n"
        return f"{header}{files}{_relink(body, name).strip()}\n\n$ARGUMENTS\n"
    raise ValueError(f"unknown stub mode {mode!r}")


def expected_stubs(root: Path, mode: str | None = None) -> dict[str, str]:
    """Return ``{stub path: content}`` for every valid skill."""
    stubs: dict[str, str] = {}
    for skill in skill_files(root):
        try:
            fields, body, _ = split_frontmatter(read(skill))
        except ValueError:
            continue
        if fields and fields.get("description"):
            name = skill.parent.name
            stubs[f"{STUBS_DIR}/{name}.md"] = render_stub(
                name, fields["description"], body, mode or STUB_MODE
            )
    return stubs


# --- build ------------------------------------------------------------------


def build(root: Path) -> list[str]:
    """Rewrite every derived view; return the paths that changed."""
    changed: list[str] = []
    for index in index_files(root):
        text = read(index)
        updated = apply_index(text, render_index(root, index))
        if updated is not None and updated != text:
            index.write_text(updated, encoding="utf-8", newline="\n")
            changed.append(rel(root, index))
    stubs = expected_stubs(root)
    stub_dir = root / STUBS_DIR
    for existing in sorted(stub_dir.glob("*.md")) if stub_dir.is_dir() else []:
        if rel(root, existing) not in stubs:
            existing.unlink()
            changed.append(rel(root, existing))
    for path, content in stubs.items():
        target = root / path
        if not target.is_file() or read(target) != content:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
            changed.append(path)
    return changed


# --- check ------------------------------------------------------------------

STALE_FIX = f"run `{BUILD_COMMAND}` and commit the result"


def check_instruction_files(root: Path) -> list[Problem]:
    problems: list[Problem] = []
    agents = root / "AGENTS.md"
    if not agents.is_file():
        return [
            Problem(
                "AGENTS.md",
                "missing",
                "AGENTS.md is the always-on map for every coding agent",
                "restore AGENTS.md at the repository root",
            )
        ]
    lines = read(agents).rstrip("\n").count("\n") + 1
    if lines > AGENTS_MD_MAX_LINES:
        problems.append(
            Problem(
                "AGENTS.md",
                f"{lines} lines, budget {AGENTS_MD_MAX_LINES}",
                "AGENTS.md stays within its size budget",
                "move detail into a linked doc or skill, or delete lines that "
                "fail the pruning test",
            )
        )
    claude = root / "CLAUDE.md"
    if claude.exists() and read(claude).strip() != CLAUDE_MD_FALLBACK:
        problems.append(
            Problem(
                "CLAUDE.md",
                "holds more than the fallback import",
                "AGENTS.md is the only instruction file",
                f"move shared instructions to AGENTS.md; the only permitted "
                f"CLAUDE.md is the single line `{CLAUDE_MD_FALLBACK}`",
            )
        )
    for path, reason in FORBIDDEN.items():
        if (root / path).exists():
            problems.append(
                Problem(
                    path,
                    "must not exist",
                    reason,
                    "delete it; docs/decisions/0001-agent-harness-layout.md "
                    "explains the layout",
                )
            )
    return problems


def check_references(root: Path, path: Path) -> list[Problem]:
    """Return broken links, anchors, and backticked paths in *path*."""
    problems: list[Problem] = []
    where = rel(root, path)
    for number, line in prose_lines(read(path)):
        prose = _CODE.sub("``", line)
        for raw in _LINK.findall(prose) + _DEFINITION.findall(prose):
            target = raw[1:-1] if raw.startswith("<") else raw
            if _EXTERNAL.match(target):
                continue
            file_part, _, anchor = target.partition("#")
            resolved = path.parent / file_part if file_part else path
            if file_part and not exists_exactly(resolved):
                problems.append(
                    Problem(
                        f"{where}:{number}",
                        f"broken link {target}",
                        "every link resolves, with exact spelling",
                        "point the link at the file's current path",
                    )
                )
            elif (
                anchor
                and resolved.suffix == ".md"
                and anchor not in anchors(read(resolved))
            ):
                problems.append(
                    Problem(
                        f"{where}:{number}",
                        f"missing anchor {target}",
                        "every link resolves, with exact spelling",
                        "use the heading's GitHub slug (lowercase, hyphens)",
                    )
                )
        for code in _CODE.findall(line):
            candidate = code.strip().split(":")[0].rstrip(".,;")
            if not candidate.startswith(REPO_ROOTS) or any(
                c in candidate for c in "*<>{} …"
            ):
                continue
            allowed = any(candidate.startswith(p) for p in PLANNED) or any(
                candidate.rstrip("/") == path for path in FORBIDDEN
            )
            if not allowed and not exists_exactly(root / candidate):
                problems.append(
                    Problem(
                        f"{where}:{number}",
                        f"missing path `{candidate}`",
                        "every backticked repository path exists",
                        "fix the path, or add a not-yet-created path to PLANNED in "
                        "scripts/docs_tool.py with its reason",
                    )
                )
    return problems


def has_content(path: Path) -> bool:
    """Return whether *path* is a file or a folder holding a file.

    Git does not track empty folders, so an empty folder exists only on the
    machine that left it behind and must not count.
    """
    if path.is_file():
        return True
    return path.is_dir() and any(child.is_file() for child in path.rglob("*"))


def check_planned(root: Path) -> list[Problem]:
    return [
        Problem(
            "scripts/docs_tool.py",
            f"PLANNED lists `{path}`, which now exists",
            "PLANNED holds only paths that do not exist yet",
            f"remove `{path}` from PLANNED",
        )
        for path in PLANNED
        if has_content(root / path)
    ]


def check_page_shape(root: Path, path: Path) -> list[Problem]:
    """Return purpose-line and table-of-contents problems for one page."""
    where = rel(root, path)
    if path.is_relative_to(root / SKILLS_DIR) or path.is_relative_to(root / STUBS_DIR):
        return []
    text = read(path)
    problems: list[Problem] = []
    title, purpose = title_and_purpose(text)
    if title is None:
        problems.append(
            Problem(
                where,
                "does not start with a '# ' title",
                "every doc opens with a title and its purpose",
                "make the first line a '# Title'",
            )
        )
    elif purpose is None or len(purpose) > PURPOSE_MAX_CHARS:
        problems.append(
            Problem(
                where,
                "no purpose paragraph under the title"
                if purpose is None
                else f"purpose paragraph has {len(purpose)} characters",
                "every doc opens with its purpose: what it covers, when to read it",
                f"write one plain paragraph of at most {PURPOSE_MAX_CHARS} characters "
                "directly under the title",
            )
        )
    lines = text.rstrip("\n").count("\n") + 1
    if lines > TOC_THRESHOLD_LINES:
        h2 = [line for _, line in prose_lines(text) if line.startswith("## ")]
        if not h2 or h2[0].strip() != "## Contents":
            problems.append(
                Problem(
                    where,
                    f"{lines} lines without a table of contents",
                    f"files over {TOC_THRESHOLD_LINES} lines open with '## Contents'",
                    "make the first '##' heading a '## Contents' list of the sections",
                )
            )
    return problems


def check_indexes(root: Path) -> list[Problem]:
    problems: list[Problem] = []
    docs = root / "docs"
    if docs.is_dir() and not (docs / "README.md").is_file():
        problems.append(
            Problem(
                "docs/README.md",
                "missing",
                "every docs folder has an index",
                "add docs/README.md with a title, a purpose paragraph, and the "
                "generated index markers",
            )
        )
    for page in doc_pages(root):
        if page.name != "README.md" and nearest_index(root, page) is None:
            problems.append(
                Problem(
                    rel(root, page),
                    "listed in no index",
                    "every docs folder has an index",
                    "add a README.md with index markers to its folder or a parent",
                )
            )
    for index in index_files(root):
        text = read(index)
        updated = apply_index(text, render_index(root, index))
        if updated is None:
            problems.append(
                Problem(
                    rel(root, index),
                    "has no generated index block",
                    "every docs folder has an index",
                    f"add the lines {INDEX_BEGIN!r} and {INDEX_END!r}, then "
                    f"run `{BUILD_COMMAND}`",
                )
            )
        elif updated != text:
            problems.append(
                Problem(
                    rel(root, index),
                    "generated index is stale",
                    "generated views match a fresh generation",
                    STALE_FIX,
                )
            )
    return problems


def check_skills(root: Path) -> list[Problem]:
    problems: list[Problem] = []
    skills = root / SKILLS_DIR
    for folder in (
        sorted(p for p in skills.iterdir() if p.is_dir()) if skills.is_dir() else []
    ):
        where = f"{SKILLS_DIR}/{folder.name}/SKILL.md"
        rule = "skills follow the Agent Skills specification"
        skill = folder / "SKILL.md"
        if not skill.is_file():
            problems.append(
                Problem(where, "missing", rule, "add SKILL.md or delete the folder")
            )
            continue
        try:
            fields, body, _ = split_frontmatter(read(skill))
        except ValueError as error:
            problems.append(
                Problem(where, str(error), rule, "use one-line `key: value` fields")
            )
            continue
        if fields is None:
            problems.append(
                Problem(
                    where,
                    "no frontmatter",
                    rule,
                    "start with ---, name, description, ---",
                )
            )
            continue
        name = fields.get("name", "")
        if (
            name != folder.name
            or not SKILL_NAME.match(name)
            or len(name) > SKILL_NAME_MAX
        ):
            problems.append(
                Problem(
                    where,
                    f"name {name!r} is invalid or differs from the folder",
                    rule,
                    f"set `name: {folder.name}`: lowercase letters, digits, hyphens, "
                    f"at most {SKILL_NAME_MAX} characters",
                )
            )
        description = fields.get("description", "")
        if not description or len(description) > SKILL_DESCRIPTION_MAX:
            problems.append(
                Problem(
                    where,
                    f"description has {len(description)} characters",
                    "a skill's description says what it does and when to use it",
                    f"write 1 to {SKILL_DESCRIPTION_MAX} characters, triggers first",
                )
            )
        unknown = sorted(set(fields) - SKILL_FIELDS)
        if unknown:
            problems.append(
                Problem(where, f"unknown fields {unknown}", rule, "remove them")
            )
        body_lines = body.rstrip("\n").count("\n") + 1
        if body_lines > SKILL_BODY_MAX_LINES:
            problems.append(
                Problem(
                    where,
                    f"body has {body_lines} lines",
                    f"SKILL.md stays under {SKILL_BODY_MAX_LINES} lines",
                    "move detail into bundled files one level deep and link them",
                )
            )
    return problems


def check_stubs(root: Path) -> list[Problem]:
    stubs = expected_stubs(root)
    stub_dir = root / STUBS_DIR
    actual = {
        rel(root, path): read(path)
        for path in (sorted(stub_dir.glob("*.md")) if stub_dir.is_dir() else [])
    }
    rule = "generated views match a fresh generation"
    problems = [
        Problem(path, "stale or missing Claude Code stub", rule, STALE_FIX)
        for path, content in stubs.items()
        if actual.get(path) != content
    ]
    problems += [
        Problem(path, "stub without a skill", rule, STALE_FIX)
        for path in actual
        if path not in stubs
    ]
    return problems


def check_plans(root: Path) -> list[Problem]:
    plans = root / "docs" / "plans"
    allowed = {plans / "active", plans / "completed"}
    return [
        Problem(
            rel(root, page),
            "plan outside docs/plans/active/ and docs/plans/completed/",
            "a plan's folder says whether it is current",
            "move it to active/ while the work runs, to completed/ when it is done",
        )
        for page in (sorted(plans.rglob("*.md")) if plans.is_dir() else [])
        if page != plans / "README.md" and page.parent not in allowed
    ]


def check(root: Path) -> list[Problem]:
    """Return every documentation rule violation under *root*."""
    problems = check_instruction_files(root) + check_planned(root)
    for path in markdown_files(root):
        problems += check_references(root, path)
        problems += check_page_shape(root, path)
    problems += check_indexes(root)
    problems += check_skills(root)
    problems += check_stubs(root)
    problems += check_plans(root)
    return problems


def main(argv: Sequence[str] | None = None, root: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["build", "check"])
    args = parser.parse_args(argv)
    base = root or Path.cwd()
    if args.command == "build":
        for path in build(base):
            print(f"wrote {path}")
        return 0
    problems = check(base)
    for problem in problems:
        print(problem.render())
    if problems:
        print(f"{len(problems)} documentation problem(s)", file=sys.stderr)
        return 1
    print("documentation rules: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
