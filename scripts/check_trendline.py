"""Trendline 실제 데이터·상호작용·1440/390px 화면 검증 (네트워크 수집 없음)."""
from pathlib import Path
import json
import tempfile

from playwright.sync_api import sync_playwright
from generate_visual_thumbnails import start_server
from serve_web import Handler


ROOT = Path(__file__).resolve().parent.parent


def reference_rates():
    fields = json.loads((ROOT / "web/data/trendline/index.json").read_text())["fields"]
    player = json.loads((ROOT / "web/data/trendline/2026/batter/players/53123.json").read_text())["games"][-10:]
    league = json.loads((ROOT / "web/data/trendline/2026/league.json").read_text())["days"]
    selected = [day for day in league if player[0]["date"] <= day["date"] <= player[-1]["date"]]

    def rate(rows):
        numerator = sum(row["counts"][fields.index("o_swings")] for row in rows)
        denominator = sum(row["counts"][fields.index("o_n")] for row in rows)
        return numerator / denominator * 100

    return rate(player), rate(selected)


def geometry(page, width):
    measured = page.evaluate("({width:innerWidth,scroll:document.documentElement.scrollWidth,margin:getComputedStyle(document.querySelector('.page-title')).marginTop,top:document.querySelector('.page-title').getBoundingClientRect().top})")
    assert measured["scroll"] == measured["width"] == width
    assert measured["margin"] == "0px"
    return measured["top"]


def check(page, base, width, output):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(base + "/trendline/", wait_until="networkidle")
    page.wait_for_selector(".trend-chart svg")
    assert page.locator("#player-name").inner_text() == "양현종"
    assert page.evaluate("state.models.find(m=>m.w.metric==='k').curves[0].points.find(p=>p.label==='2024').value") > 5
    title_top = geometry(page, width)
    page.screenshot(path=str(output / f"trendline-pitcher-{width}.png"), full_page=True)
    page.locator("#query").fill("클레빈저")
    page.locator("#search-form").evaluate("form=>form.requestSubmit()")
    page.wait_for_function("state.selected?.id==='56939'")
    assert page.locator(".trend-point").count() > 0
    page.locator("#role").select_option("batter")
    page.wait_for_function("state.selected?.id==='53123'")
    assert page.locator(".trend-card").count() == 4
    assert page.locator(".league-line").count() == 3
    page.locator(".league-toggle").first.uncheck()
    assert page.locator(".league-line").count() == 2
    page.locator(".league-toggle").first.check()
    page.evaluate("window.scrollTo(0,0)")
    page.screenshot(path=str(output / f"trendline-batter-{width}.png"), full_page=True)
    first = page.locator(".trend-card").first
    first.locator('[data-setting="metric"]').select_option("k")
    assert first.locator('[data-setting="pitch"]').is_disabled()
    first.locator('[data-setting="metric"]').select_option("o_swing")
    for _ in range(2):
        page.locator("#add-widget").click()
    assert page.locator(".trend-card").count() == 6 and page.locator("#add-widget").is_disabled()
    page.locator(".trend-remove").last.click()
    assert page.locator(".trend-card").count() == 5 and page.locator("#add-widget").is_enabled()
    page.locator("#view").select_option("game")
    page.locator('.trend-card [data-setting="window"]').first.select_option("10")
    actual = page.evaluate("state.models[0].curves[0].points.at(-1)")
    expected, league = reference_rates()
    assert abs(actual["value"] - expected) < 1e-9
    assert abs(actual["league"]["value"] - league) < 1e-9
    first.locator(".trend-chart").focus()
    first.locator(".trend-chart").press("ArrowRight")
    dates = page.locator(".trend-detail > strong:first-child").all_text_contents()
    assert len(set(dates)) == 1
    geometry(page, width)
    page.evaluate("window.scrollTo(0,0)")
    page.screenshot(path=str(output / f"trendline-rolling-{width}.png"), full_page=True)
    page.locator("#view").select_option("month")
    assert first.locator('[data-setting="window"]').is_disabled()
    page.locator("#from").fill("2026-10-06")
    page.locator("#to").fill("2026-01-01")
    assert "확인" in page.locator("#period-note").inner_text() and page.locator(".trend-card").count() == 0
    page.locator('[data-period="current"]').click()
    assert page.locator(".trend-card").count() == 5
    # A selected doubleheader has two outings at the same x coordinate.
    page.evaluate("""() => {
        const game = state.games.at(-1);
        state.games = [game, {...game, game_id: game.game_id + '-second'}];
        document.querySelector('#view').value = 'game';
        document.querySelector('#from').value = game.date;
        document.querySelector('#to').value = game.date;
        renderWidgets();
    }""")
    assert page.evaluate("state.models[0].bins.length") == 2
    assert not page.evaluate("[...document.querySelectorAll('.trend-chart svg')].some(svg => /NaN|Infinity/.test(svg.innerHTML))")
    page.goto(base + "/pitch-arsenal/", wait_until="networkidle")
    assert geometry(page, width) == title_top
    assert not errors, errors


def main():
    Handler.log_message = lambda *args: None
    output = Path(tempfile.mkdtemp(prefix="trendline-check-"))
    server, base = start_server()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for width in [1440, 390]:
                page = browser.new_page(viewport={"width": width, "height": 1000}, locale="ko-KR")
                check(page, base, width, output)
                page.close()
            page = browser.new_page()
            page.route("**/data/trendline/2026/league.json", lambda route: route.fulfill(status=500, body="unavailable"))
            page.goto(base + "/trendline/", wait_until="networkidle")
            assert page.locator("#profile").is_hidden() and "불러오지 못" in page.locator("#status").inner_text()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print(f"Trendline 통과: 지표·리그 창·검색·위젯·커서·실패 처리·1440/390px. 화면: {output}")


if __name__ == "__main__":
    main()
