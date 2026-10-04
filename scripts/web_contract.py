"""web/ 도구 페이지가 공통 규격(헤더·폭·제목 블록·캐시 버스터)을 지키는지 검사합니다.

    python scripts/web_contract.py          # 위반이 있으면 목록을 출력하고 exit 1

규격은 theme.css·site-header.js가 정의하고, 각 페이지는 아래 마크업만 맞추면 따라옵니다.
새 도구는 scripts/new_web_tool.py로 만들면 처음부터 규격을 지킵니다.

- <body> 맨 앞에서 ../site-header.js를 동기 로드 (브랜드 줄 + 메뉴 줄)
- <main class="site-main"> 하나 (헤더와 같은 1440px 폭·좌우 여백)
- 도구 페이지는 .page-title 블록(eyebrow + h1 + 부제). 홈은 예외
- theme.css는 페이지 전용 CSS 뒤에 로드 (movement-zones만 예외, CLAUDE.md 참고)
- 로컬 CSS/JS에는 ?v=YYYYMMDD-N 캐시 버스터, theme.css·site-header.js 버전은 전 페이지 동일
- site-header.js의 TOOLS/ALIASES와 web/<tool>/index.html 목록이 일치
"""
from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
# 데이터·이미지 디렉터리는 페이지가 아닙니다.
NON_PAGE_DIRS = {"data", "assets"}
# theme.css를 페이지 CSS보다 먼저 로드하는 기존 예외 (CLAUDE.md "웹 페이지 구조").
THEME_FIRST_ALLOWED = {"movement-zones"}
VERSION = re.compile(r"\?v=\d{8}-\d+$")


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.events.append((tag, {k: v or "" for k, v in attrs}))


def _classes(attrs: dict[str, str]) -> set[str]:
    return set(attrs.get("class", "").split())


def _is_local(url: str) -> bool:
    return not re.match(r"^(https?:)?//", url)


def page_problems(path: Path, web_root: Path = WEB_ROOT) -> list[str]:
    """한 페이지의 규격 위반 목록. 빈 리스트면 통과."""
    name = path.parent.name if path.parent != web_root else ""
    is_home = path.parent == web_root
    parser = _PageParser()
    parser.feed(path.read_text(encoding="utf-8"))
    events = parser.events
    rel = path.relative_to(web_root).as_posix()
    problems: list[str] = []

    def fail(message: str) -> None:
        problems.append(f"{rel}: {message}")

    tags = [tag for tag, _ in events]
    body_at = tags.index("body") if "body" in tags else -1
    after_body = [(t, a) for t, a in events[body_at + 1:]]
    if not after_body or after_body[0][0] != "script" or not after_body[0][1].get("src", "").split("?")[0].endswith("site-header.js"):
        fail("<body> 첫 요소가 site-header.js <script>가 아닙니다")

    mains = [a for t, a in events if t == "main"]
    if len(mains) != 1 or "site-main" not in _classes(mains[0]):
        fail('<main class="site-main">이 정확히 하나 있어야 합니다')

    if not is_home:
        title_index = next((i for i, (_, a) in enumerate(events) if "page-title" in _classes(a)), None)
        if title_index is None:
            fail(".page-title 제목 블록이 없습니다")
        else:
            rest = events[title_index + 1:]
            if not any("eyebrow" in _classes(a) for _, a in rest[:6]):
                fail(".page-title 안에 .eyebrow가 없습니다")
            if not any(t == "h1" or "search-title" in _classes(a) for t, a in rest[:6]):
                fail(".page-title 안에 <h1>(또는 .search-title)이 없습니다")

    stylesheets = [a.get("href", "") for t, a in events if t == "link" and a.get("rel") == "stylesheet"]
    scripts = [a.get("src", "") for t, a in events if t == "script" and a.get("src")]
    for url in stylesheets + scripts:
        if _is_local(url) and not VERSION.search(url):
            fail(f"캐시 버스터(?v=YYYYMMDD-N)가 없습니다: {url}")

    theme_at = next((i for i, url in enumerate(stylesheets) if url.split("?")[0].endswith("theme.css")), None)
    if theme_at is None:
        fail("theme.css를 로드하지 않습니다")
    elif theme_at != len(stylesheets) - 1 and name not in THEME_FIRST_ALLOWED:
        fail("theme.css는 페이지 전용 CSS 뒤(마지막)에 로드해야 합니다")
    return problems


def shared_versions(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    found = {}
    for asset in ("theme.css", "site-header.js"):
        match = re.search(re.escape(asset) + r"\?v=([\w-]+)", text)
        if match:
            found[asset] = match.group(1)
    return found


def nav_entries(web_root: Path = WEB_ROOT) -> tuple[list[str], list[str]]:
    """site-header.js의 TOOLS 경로와 ALIASES 키(하위 페이지) 목록."""
    source = (web_root / "site-header.js").read_text(encoding="utf-8")
    tools_block = re.search(r"const TOOLS = \[(.*?)\];", source, re.S).group(1)
    tools = re.findall(r'\["([\w-]+)/",', tools_block)
    aliases_block = re.search(r"const ALIASES = \{(.*?)\};", source, re.S).group(1)
    aliases = re.findall(r'"([\w-]+)/"\s*:', aliases_block)
    return tools, aliases


def pages(web_root: Path = WEB_ROOT) -> list[Path]:
    found = [web_root / "index.html"]
    found += sorted(p for p in web_root.glob("*/index.html") if p.parent.name not in NON_PAGE_DIRS)
    return found


def site_problems(web_root: Path = WEB_ROOT) -> list[str]:
    problems: list[str] = []
    all_pages = pages(web_root)
    for path in all_pages:
        problems += page_problems(path, web_root)

    versions = {path.relative_to(web_root).as_posix(): shared_versions(path) for path in all_pages}
    for asset in ("theme.css", "site-header.js"):
        distinct = {v.get(asset) for v in versions.values()}
        if len(distinct) > 1:
            detail = ", ".join(f"{page}={v.get(asset)}" for page, v in versions.items())
            problems.append(f"{asset} 캐시 버스터가 페이지마다 다릅니다 (한꺼번에 올려야 합니다): {detail}")

    tools, aliases = nav_entries(web_root)
    tool_dirs = {path.parent.name for path in all_pages if path.parent != web_root}
    for missing in sorted(set(tools) - tool_dirs):
        problems.append(f"site-header.js TOOLS의 {missing}/에 index.html이 없습니다")
    for orphan in sorted(tool_dirs - set(tools) - set(aliases)):
        problems.append(f"web/{orphan}/ 이 site-header.js TOOLS(또는 ALIASES)에 없습니다")
    return problems


def main() -> int:
    problems = site_problems()
    for problem in problems:
        print(problem)
    if problems:
        print(f"\n웹 규격 위반 {len(problems)}건", file=sys.stderr)
        return 1
    print(f"웹 규격 통과: 페이지 {len(pages())}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
