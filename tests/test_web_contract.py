import importlib.util
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("new_web_tool", ROOT / "scripts" / "new_web_tool.py")
new_web_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(new_web_tool)
from web_contract import nav_entries, page_problems, site_problems  # noqa: E402


def copy_pages(tmp_path):
    """데이터·이미지를 뺀 web/ 사본 (페이지·CSS·JS만)."""
    web = tmp_path / "web"
    shutil.copytree(ROOT / "web", web, ignore=shutil.ignore_patterns("data", "assets", "*.png", "*.webp"))
    return web


def test_current_pages_follow_contract():
    assert site_problems() == []


def test_scaffolded_tool_follows_contract(tmp_path):
    web = copy_pages(tmp_path)
    target = new_web_tool.create_tool(web, "strike-zone", "Strike Zone", "pitching", "투수별 판정", "Strike Zone", "20991231")

    assert site_problems(web) == []
    assert "strike-zone" in nav_entries(web)[0]
    html = (target / "index.html").read_text(encoding="utf-8")
    assert '<main class="site-main">' in html and 'class="page-title"' in html and ">PITCHING<" in html
    # 메뉴가 바뀌었으므로 모든 페이지의 site-header.js 버전이 함께 올라가야 합니다.
    assert all("site-header.js?v=20991231-1" in p.read_text(encoding="utf-8") for p in web.glob("**/index.html"))


def test_contract_catches_common_mistakes(tmp_path):
    web = copy_pages(tmp_path)
    page = web / "zones" / "index.html"
    text = page.read_text(encoding="utf-8")
    broken = (text.replace('class="site-main"', "")
                  .replace('class="page-title"', "")
                  .replace("zone.css?v=", "zone.css?x="))
    page.write_text(broken, encoding="utf-8")
    problems = " ".join(page_problems(page, web))
    assert "site-main" in problems and ".page-title" in problems and "캐시 버스터" in problems


def test_unregistered_tool_directory_is_reported(tmp_path):
    web = copy_pages(tmp_path)
    new_web_tool.create_tool(web, "orphan-tool", "Orphan", "test", "메뉴 없음", None, "20991231")
    assert any("orphan-tool" in problem for problem in site_problems(web))


def test_next_version_increments_same_day():
    assert new_web_tool.next_version("20991231-3", "20991231") == "20991231-4"
    assert new_web_tool.next_version("20991230-3", "20991231") == "20991231-1"
