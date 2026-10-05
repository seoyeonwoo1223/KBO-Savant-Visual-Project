"""지식 저장소 센서: 하네스 문서 사이의 상대 링크와 CLAUDE.md의 @import가 실제 파일을 가리키는지 검사합니다.

문서를 옮기거나 이름을 바꾸면 에이전트가 따라갈 지도가 끊깁니다(docs/decisions/0011-harness-structure.md).
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = [ROOT / "AGENTS.md", ROOT / "CLAUDE.md", ROOT / "README.md", ROOT / "docs" / "conventions.md",
        ROOT / "docs" / "architecture.md", *sorted((ROOT / "docs" / "harness").glob("*.md")),
        *sorted((ROOT / "docs" / "decisions").glob("*.md"))]
LINK = re.compile(r"\]\(([^)\s]+)\)")


@pytest.mark.parametrize("doc", DOCS, ids=lambda path: path.relative_to(ROOT).as_posix())
def test_relative_links_resolve(doc):
    broken = []
    for target in LINK.findall(doc.read_text(encoding="utf-8")):
        if re.match(r"^[a-z]+:", target) or target.startswith("#"):
            continue
        path = (doc.parent / target.split("#")[0]).resolve()
        if not path.exists():
            broken.append(target)
    assert not broken, f"{doc.relative_to(ROOT)}의 링크가 없는 파일을 가리킵니다: {broken}"


def test_claude_md_imports_agents_md():
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    imports = re.findall(r"^@(\S+)$", text, re.M)
    assert imports == ["AGENTS.md"] and (ROOT / "AGENTS.md").is_file(), "CLAUDE.md는 @AGENTS.md만 불러와야 합니다 (지시 문서는 한 곳)"


def test_decision_index_lists_every_record():
    index = (ROOT / "docs" / "decisions" / "README.md").read_text(encoding="utf-8")
    records = [p.name for p in (ROOT / "docs" / "decisions").glob("[0-9][0-9][0-9][0-9]-*.md")]
    missing = [name for name in records if f"({name})" not in index]
    assert not missing, f"docs/decisions/README.md 목록에 없는 결정 기록: {missing}"
