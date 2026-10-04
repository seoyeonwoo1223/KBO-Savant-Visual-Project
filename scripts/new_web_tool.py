"""새 웹 도구 web/<slug>/를 공통 규격대로 만들고 상단 메뉴에 등록합니다.

    python scripts/new_web_tool.py strike-zone --title "Strike Zone" \\
        --eyebrow "PITCHING" --subtitle "투수별 스트라이크존 판정"

만드는 것
- web/<slug>/index.html  공통 헤더·site-main·.page-title·캐시 버스터가 들어간 골격
- web/<slug>/<slug>.css  도구 전용 레이아웃 (폭·제목·헤더는 theme.css가 맡으므로 쓰지 않음)
- web/<slug>/<slug>.js   데이터 로드 자리

바꾸는 것
- site-header.js의 TOOLS 끝에 메뉴 항목 추가 (--no-nav로 생략)
- 홈(web/index.html) 마지막 카드 뒤에 같은 이름의 카드 추가. 그림은 빈 자리 표시이므로
  scripts/visual_thumbnails.json에 캡처 설정을 넣고 썸네일을 만든 뒤 <img>로 바꿉니다
- 메뉴가 바뀌므로 모든 페이지의 site-header.js ?v= 를 함께 올림

만든 뒤 python scripts/web_contract.py 로 규격을 확인합니다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from web_contract import WEB_ROOT, nav_entries, pages, shared_versions  # noqa: E402

SLUG = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

INDEX_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>KBO {title}</title>
  <link rel="stylesheet" href="{slug}.css?v={asset_v}">
  <link rel="stylesheet" href="../theme.css?v={theme_v}">
</head>
<body>
  <script src="../site-header.js?v={header_v}"></script>
  <main class="site-main">
    <header class="page-title">
      <p class="eyebrow">{eyebrow}</p>
      <h1>{title}</h1>
      <p>{subtitle}</p>
    </header>
    <section class="tool-panel" aria-label="{title}">
      <p id="status" class="status">데이터를 불러오는 중입니다.</p>
    </section>
  </main>
  <script src="{slug}.js?v={asset_v}"></script>
</body>
</html>
"""

CSS_TEMPLATE = """/* {title} 전용 레이아웃. theme.css를 뒤에 로드합니다.
   페이지 폭·좌우 여백(main.site-main), 제목 블록(.page-title), 공통 헤더는 theme.css가 정하므로
   여기서 main이나 header/h1/nav 같은 태그 선택자를 꾸미지 마십시오. 색은 --kbo-* 토큰을 씁니다. */
:root {{ font-family: Arial, Helvetica, sans-serif; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; }}

.tool-panel {{ padding: 20px; border: 1px solid var(--kbo-line); background: var(--kbo-card); }}
.status {{ margin: 0; color: var(--kbo-muted); font-size: .9rem; }}

@media (max-width: 720px) {{
  .tool-panel {{ padding: 14px; }}
}}
"""

JS_TEMPLATE = """// {title}. 데이터는 페이지 기준 ../data/<metric>/<season>/… 을 fetch합니다 (CLAUDE.md "웹 페이지 구조").
// canvas를 숨겨진 탭에 그릴 때는 폭이 0이므로 직전 CSS 폭을 쓰십시오 (zone-awareness.js canvasContext 참고).
(function () {{
  const status = document.querySelector("#status");
  status.textContent = "준비 중입니다.";
}})();
"""


def next_version(current: str | None, today: str) -> str:
    """같은 날 이미 올린 버전이면 -N을 하나 올리고, 아니면 오늘-1."""
    match = re.fullmatch(r"(\d{8})-(\d+)", current or "")
    if match and match.group(1) == today:
        return f"{today}-{int(match.group(2)) + 1}"
    return f"{today}-1"


def register_nav(web_root: Path, slug: str, label: str) -> None:
    path = web_root / "site-header.js"
    source = path.read_text(encoding="utf-8")
    block = re.search(r"(const TOOLS = \[\n)(.*?)(\n\s*\];)", source, re.S)
    entry = f'    ["{slug}/", "{label}"],'
    source = source[:block.end(2)] + "\n" + entry + source[block.end(2):]
    path.write_text(source, encoding="utf-8")


HOME_CARD_TEMPLATE = """        <a class="visual-card" href="{slug}/">
          <div class="visual-art" aria-hidden="true"></div>
          <div class="visual-card__body"><h3>{label}</h3><p>{subtitle}</p><b>열기 →</b></div>
        </a>
"""


def add_home_card(web_root: Path, slug: str, label: str, subtitle: str) -> None:
    """메뉴 순서와 홈 카드 순서가 같아야 하므로, 메뉴 끝에 붙인 도구는 마지막 카드 뒤에 둡니다."""
    path = web_root / "index.html"
    source = path.read_text(encoding="utf-8")
    end = source.rindex("</a>\n") + len("</a>\n")
    card = HOME_CARD_TEMPLATE.format(slug=slug, label=html.escape(label), subtitle=html.escape(subtitle))
    path.write_text(source[:end] + card + source[end:], encoding="utf-8")


def bump_header_version(web_root: Path, today: str) -> str:
    current = shared_versions(web_root / "index.html").get("site-header.js")
    new = next_version(current, today)
    for page in pages(web_root):
        text = page.read_text(encoding="utf-8")
        page.write_text(re.sub(r"site-header\.js\?v=[\w-]+", f"site-header.js?v={new}", text), encoding="utf-8")
    return new


def create_tool(web_root: Path, slug: str, title: str, eyebrow: str, subtitle: str,
                nav_label: str | None, today: str) -> Path:
    if not SLUG.match(slug):
        raise SystemExit(f"slug는 소문자 kebab-case여야 합니다: {slug}")
    target = web_root / slug
    if target.exists():
        raise SystemExit(f"이미 있습니다: {target}")
    tools, aliases = nav_entries(web_root)
    if slug in tools or slug in aliases:
        raise SystemExit(f"site-header.js에 이미 등록된 경로입니다: {slug}/")

    if nav_label:
        register_nav(web_root, slug, nav_label)
        add_home_card(web_root, slug, nav_label, subtitle)
        bump_header_version(web_root, today)
    shared = shared_versions(web_root / "index.html")
    escaped = {"title": html.escape(title), "eyebrow": html.escape(eyebrow.upper()), "subtitle": html.escape(subtitle)}

    target.mkdir()
    (target / "index.html").write_text(INDEX_TEMPLATE.format(
        slug=slug, asset_v=f"{today}-1", theme_v=shared["theme.css"], header_v=shared["site-header.js"], **escaped,
    ), encoding="utf-8")
    (target / f"{slug}.css").write_text(CSS_TEMPLATE.format(title=title), encoding="utf-8")
    (target / f"{slug}.js").write_text(JS_TEMPLATE.format(title=title), encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("slug", help="web/<slug>/ 디렉터리 이름 (kebab-case)")
    parser.add_argument("--title", required=True, help="<h1> 제목 (영문, 메뉴 이름과 맞추기를 권장)")
    parser.add_argument("--eyebrow", required=True, help="제목 위 작은 분류 라벨 (대문자로 바뀜)")
    parser.add_argument("--subtitle", required=True, help="제목 아래 한 줄 설명 (한국어)")
    parser.add_argument("--nav-label", help="상단 메뉴 이름 (기본: --title)")
    parser.add_argument("--no-nav", action="store_true", help="메뉴에 등록하지 않음 (하위 페이지 등)")
    parser.add_argument("--web-root", type=Path, default=WEB_ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--date", default=dt.date.today().strftime("%Y%m%d"), help=argparse.SUPPRESS)
    args = parser.parse_args()

    nav_label = None if args.no_nav else (args.nav_label or args.title)
    target = create_tool(args.web_root, args.slug, args.title, args.eyebrow, args.subtitle, nav_label, args.date)
    print(f"생성: {target}")
    if args.no_nav:
        print("메뉴 미등록: site-header.js ALIASES에 상위 도구를 지정해야 web_contract가 통과합니다.")
    else:
        print("홈 카드는 그림 없이 추가했습니다: scripts/visual_thumbnails.json에 캡처 설정 → 썸네일 생성 → 카드에 <img> 지정")
    print("다음 단계: python scripts/web_contract.py → python scripts/serve_web.py로 확인")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
