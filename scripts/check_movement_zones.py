"""Verify the generated data and the real browser page, without network services.

    python scripts/check_movement_zones.py
Requires the project's Playwright Chromium (playwright install chromium).
"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from threading import Thread

import numpy as np
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from visualbaseball.curated import source_sha256
from visualbaseball.metric_state import needs_build


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    data = json.loads((ROOT / "web/data/movement_zones/profiles.json").read_text(encoding="utf-8"))
    assert not needs_build(ROOT, 2026, "movement_zones"), "Artifact does not match current source/input hashes"
    expected_seasons = sorted(int(p.name.split("=")[1]) for p in (ROOT / "data/curated/pitches").glob("season=*"))
    assert data["seasons"] == expected_seasons
    assert sum(s["eligible_swings"] for s in data["sources"]) == data["swings"]
    assert sum(s["trackman_swings"] for s in data["sources"]) == data["trackman_swings"]
    for source in data["sources"]:
        assert source["eligible_swings"] > 0, f"Season dropped: {source['season']}"
        assert source["eligible_swings"] + sum(source["exclusion_counts"].values()) == source["vb_pitches"]
        for name, digest in source["code_sha256"].items():
            path = (ROOT / "analysis/movement_calibration" if name == "match_trackman.py" else
                    ROOT / "scripts" if name == "build_trackman_id_crosswalk.py" else ROOT / "src/visualbaseball") / name
            assert source_sha256(path) == digest, f"Source changed since fitting: {name}"
    total = supported = 0
    for pitch in data["pitches"].values():
        for hand in pitch["hands"].values():
            assert len(hand["profiles"]) == data["angle_max"] - data["angle_min"] + 1
            for index, profile in enumerate(hand["profiles"]):
                total += 1
                assert profile["angle"] == data["angle_min"] + index
                if profile["zones"] is None:
                    assert profile["swings"] < data["min_swings"] or profile["pitchers"] < data["min_pitchers"]
                    continue
                supported += 1
                zones = profile["zones"]
                assert zones["elite"]["whiff_pct"] >= zones["average"]["whiff_pct"] >= zones["dead"]["whiff_pct"]
                for zone in zones.values():
                    assert np.isfinite([*zone["center"], *zone["hb"], *zone["ivb"], zone["whiff_pct"]]).all()
                    assert np.linalg.eigvalsh(zone["covariance"]).min() > 0
    assert supported > 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(ROOT / "web")))
    Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/movement-zones/"
    output = ROOT / ".cache/movement_zones"
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(url)
            page.wait_for_selector("#angle:not([disabled])")
            checked = page.evaluate("""async () => {
              const d = await (await fetch('../data/movement_zones/profiles.json')).json();
              const slider = document.querySelector('#angle');
              let checked = 0;
              for (const hand of ['R','L']) {
                document.querySelector(`[data-hand="${hand}"]`).click();
                for (const [code,pitch] of Object.entries(d.pitches)) {
                  document.querySelector(`[data-pitch="${code}"]`).click();
                  for (const p of pitch.hands[hand].profiles) {
                    slider.value = p.angle;
                    slider.dispatchEvent(new Event('input'));
                    const zones = document.querySelectorAll('#movement-chart .zone');
                    if (zones.length !== (p.zones ? 3 : 0)) throw Error(`zones ${hand}/${code}/${p.angle}`);
                    if (document.querySelector('#angle-value').textContent !== `${p.angle}°`) throw Error('angle');
                    if (/NaN|Infinity/.test(document.querySelector('#movement-chart').innerHTML)) throw Error('nonfinite SVG');
                    if (p.zones) {
                      const dead = document.querySelector('.zone-dead');
                      const expectedHB = p.zones.dead.center[0] * (hand === 'R' ? -1 : 1);
                      if (Math.abs(Number(dead.dataset.centerHb)-expectedHB) > 1e-6) throw Error('HB sign or wrong profile');
                      if (Number(dead.dataset.centerIvb) !== p.zones.dead.center[1]) throw Error('IVB profile');
                      if (Number(dead.dataset.whiff) !== p.zones.dead.whiff_pct) throw Error('Whiff profile');
                    }
                    checked++;
                  }
                }
              }
              return checked;
            }""")
            assert checked == total
            page.goto(url + "?angle=45&hand=R&pitch=FF")
            page.wait_for_selector(".zone-dead")
            before = page.locator(".zone-dead").get_attribute("transform")
            page.locator("#angle").focus()
            page.keyboard.press("ArrowRight")
            assert page.locator("#angle").input_value() == "46"
            assert page.locator(".zone-dead").get_attribute("transform") != before
            page.locator("#play").click()
            page.wait_for_function("document.querySelector('#angle').value !== '46'")
            page.locator("#angle").focus()
            page.keyboard.press("ArrowLeft")
            assert page.locator("#play").get_attribute("aria-pressed") == "false"
            if data["pitches"].get("ST", {}).get("validation") is None and "ST" in data["pitches"]:
                page.locator('[data-pitch="ST"]').click()
                assert "시간 검증 표본 부족" in page.locator("#sample-status").inner_text()
            if data["pitches"]["FC"]["validation"]["movement"]["log_loss"] >= data["pitches"]["FC"]["validation"]["controls_only"]["log_loss"]:
                page.locator('[data-pitch="FC"]').click()
                assert "예측 개선 미확인" in page.locator("#sample-status").inner_text()
            page.goto(url + "?angle=45&hand=R&pitch=FF")
            page.wait_for_selector(".zone-dead")
            page.screenshot(path=str(output / "preview-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile page overflows"
            page.screenshot(path=str(output / "preview-mobile.png"), full_page=True)
            page.goto(url + "?angle=999&hand=L&pitch=invalid")
            page.wait_for_selector("#angle:not([disabled])")
            assert int(page.locator("#angle").input_value()) == data["angle_max"]
            page.goto(url + "?thumb=1&angle=45&hand=L&pitch=FF")
            page.wait_for_selector('[data-thumbnail-ready="true"]')
            page.route("**/data/movement_zones/profiles.json*", lambda route: route.fulfill(status=404, body="missing"))
            page.goto(url)
            page.wait_for_function("document.querySelector('#sample-status').textContent.includes('HTTP 404')")
            assert page.locator("#angle").is_disabled() and page.locator("#play").is_disabled()
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown(); server.server_close()
    evidence = {"seasons": data["seasons"], "swings": data["swings"], "trackman_swings": data["trackman_swings"],
                "profiles_checked_in_browser": checked, "supported_profiles": supported,
                "holdout": {code: pitch["validation"] for code, pitch in data["pitches"].items()}}
    (output / "validation.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
