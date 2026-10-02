"""Verify fitted artifacts and every real browser profile, locally or after deployment.

    python scripts/check_movement_zones.py [--url https://.../movement-zones/]
Requires the project's Playwright Chromium (playwright install chromium).
"""
import argparse
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


def main(url=None):
    data = json.loads((ROOT / "web/data/movement_zones/profiles.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == 2
    assert not needs_build(ROOT, 2026, "movement_zones"), "Artifact does not match current source/input hashes"
    expected_seasons = sorted(int(p.name.split("=")[1]) for p in (ROOT / "data/curated/pitches").glob("season=*"))
    assert data["seasons"] == expected_seasons
    for key in ["eligible_swings", "trackman_swings", "shape_pitches", "trackman_shape_pitches"]:
        assert sum(s[key] for s in data["sources"]) == data["swings" if key == "eligible_swings" else key]
    for source in data["sources"]:
        assert source["eligible_swings"] > 0, f"Season dropped: {source['season']}"
        assert source["eligible_swings"] + sum(source["exclusion_counts"].values()) == source["vb_pitches"]
        assert source["shape_pitches"] + sum(source["shape_exclusion_counts"].values()) == source["vb_pitches"]
        for name, digest in source["code_sha256"].items():
            path = (ROOT / "analysis/movement_calibration" if name == "match_trackman.py" else
                    ROOT / "scripts" if name == "build_trackman_id_crosswalk.py" else ROOT / "src/visualbaseball") / name
            assert source_sha256(path) == digest, f"Source changed since fitting: {name}"
    total = supported = expected_supported = 0
    for pitch in data["pitches"].values():
        for hand in pitch["hands"].values():
            assert len(hand["profiles"]) == data["angle_max"] - data["angle_min"] + 1
            for index, profile in enumerate(hand["profiles"]):
                total += 1
                assert profile["angle"] == data["angle_min"] + index
                expected = profile["expected"]
                if expected:
                    expected_supported += 1
                    assert profile["shape_pitches"] >= data["min_swings"] and profile["shape_pitchers"] >= data["min_pitchers"]
                    assert np.isfinite([*expected["center"], expected["hra"], expected["vra"], expected["flight"]]).all()
                    assert np.linalg.eigvalsh(expected["covariance"]).min() > 0
                    model = hand["expectation_model"]
                    release = np.array([profile["angle"], expected["hra"], expected["vra"], expected["flight"]]) / [45, 5, 5, .4]
                    center = np.asarray(model["movement_mean"]) + np.asarray(model["coefficients"]) @ (release - model["release_mean"])
                    np.testing.assert_allclose(center, expected["center"], atol=.000051, rtol=0)
                else:
                    assert profile["shape_pitches"] < data["min_swings"] or profile["shape_pitchers"] < data["min_pitchers"]
                if profile["zones"] is None:
                    assert not expected or profile["swings"] < data["min_swings"] or profile["pitchers"] < data["min_pitchers"]
                    continue
                supported += 1
                zones = profile["zones"]
                assert zones["high"]["whiff_pct"] >= zones["average"]["whiff_pct"] >= zones["low"]["whiff_pct"]
                used = set()
                for zone in zones.values():
                    assert np.isfinite([*zone["center"], *zone["hb"], *zone["ivb"], zone["whiff_pct"]]).all()
                    cells = set(zone["cells"])
                    assert cells and len(cells) == len(zone["cells"]) and not used.intersection(cells)
                    assert min(cells) >= 0 and max(cells) < 61 * 56
                    used.update(cells)
                    coords = np.array([[c // 56 - 30, c % 56 - 25] for c in cells])
                    np.testing.assert_array_equal(zone["hb"], [coords[:, 0].min()-.5, coords[:, 0].max()+.5])
                    np.testing.assert_array_equal(zone["ivb"], [coords[:, 1].min()-.5, coords[:, 1].max()+.5])
    assert supported > 0 and expected_supported >= supported
    server = None
    remote = bool(url)
    if not url:
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
            page.set_default_timeout(300000)
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(url)
            page.wait_for_selector("#angle:not([disabled])")
            served = page.evaluate("async () => await (await fetch('../data/movement_zones/profiles.json?verification='+Date.now())).json()")
            assert served == data, "Served data differs from the current generated artifact"
            checked = page.evaluate("""async () => {
              const d = await (await fetch('../data/movement_zones/profiles.json')).json();
              const slider = document.querySelector('#angle'), view = document.querySelector('#view');
              let checked = 0;
              for (const mode of ['expected','whiff']) {
                view.value = mode; view.dispatchEvent(new Event('change'));
                for (const hand of ['R','L']) {
                  document.querySelector(`[data-hand="${hand}"]`).click();
                  for (const [code,pitch] of Object.entries(d.pitches)) {
                    document.querySelector(`[data-pitch="${code}"]`).click();
                    for (const p of pitch.hands[hand].profiles) {
                      slider.value = p.angle; slider.dispatchEvent(new Event('input'));
                      const regions = document.querySelectorAll(mode === 'expected' ? '.expected-region' : '.zone');
                      if (regions.length !== (mode === 'expected' ? (p.expected ? 2 : 0) : (p.zones ? 3 : 0))) throw Error(`regions ${mode}/${hand}/${code}/${p.angle}`);
                      if (document.querySelector('#angle-value').textContent !== `${p.angle}°`) throw Error('angle');
                      if (/NaN|Infinity/.test(document.querySelector('#movement-chart').innerHTML)) throw Error('nonfinite SVG');
                      for (const region of regions) {
                        const z = mode === 'expected' ? p.expected : p.zones[Array.from(region.classList).find(c=>c.startsWith('zone-')).slice(5)];
                        const hb = z.center[0] * (hand === 'R' ? -1 : 1);
                        if (Math.abs(Number(region.dataset.centerHb)-hb) > 1e-6 || Number(region.dataset.centerIvb) !== z.center[1]) throw Error('HB sign or wrong profile');
                        if (mode === 'whiff') {
                          if (region.querySelector('ellipse')) throw Error('Performance ellipse returned');
                          if (region.dataset.cells !== z.cells.join(',')) throw Error('Wrong cell contour');
                          if (Number(region.dataset.whiff) !== z.whiff_pct) throw Error('Whiff profile');
                        }
                      }
                      checked++;
                    }
                  }
                }
              }
              return checked;
            }""")
            assert checked == total * 2
            # Independently query SVG geometry at every grid-cell center.
            geometry = page.evaluate("""async () => {
              const d=await (await fetch('../data/movement_zones/profiles.json')).json();
              const view=document.querySelector('#view'), slider=document.querySelector('#angle');
              document.querySelector('[data-hand="R"]').click(); slider.value=45;slider.dispatchEvent(new Event('input'));
              let samples=0, wrongGradeCells=0;
              for(const code of ['FF','SI','FC','SL','FS']) {
                document.querySelector(`[data-pitch="${code}"]`).click();
                const p=d.pitches[code].hands.R.profiles[45-d.angle_min];
                for(const mode of ['expected','whiff']) {
                  view.value=mode;view.dispatchEvent(new Event('change'));
                  const svg=document.querySelector('#movement-chart');
                  for(let h=-30;h<=30;h++) for(let v=-25;v<=30;v++) {
                    const point=svg.createSVGPoint(); point.x=92+(-h+30)*(616/60);point.y=574-(v+25)*(520/55);
                    if(mode==='whiff'&&p.zones) {
                      for(const [key,z] of Object.entries(p.zones)) {
                        const filled=svg.querySelector(`.zone-${key} .zone-fill`).isPointInFill(point);
                        wrongGradeCells+=Number(filled!==z.cells.includes((h+30)*56+v+25));
                        samples++;
                      }
                    } else if(p.expected) {
                      const e=p.expected,dh=h-e.center[0],dv=v-e.center[1],[[xx,xy],[,yy]]=e.covariance;
                      const dist=(yy*dh*dh-2*xy*dh*dv+xx*dv*dv)/(xx*yy-xy*xy);
                      for(const level of d.expected_levels) {
                        const ellipse=svg.querySelector(`.expected-${Math.round(level*100)} ellipse`);
                        const local=point.matrixTransform(svg.getCTM()).matrixTransform(ellipse.getCTM().inverse());
                        if(Math.abs(dist+2*Math.log(1-level))>.00001 && ellipse.isPointInFill(local)!==(dist<=-2*Math.log(1-level))) throw Error(`Wrong conditional ellipse ${code}/${level}/${h}/${v}`);
                        samples++;
                      }
                    }
                  }
                }
              }
              return {grid_geometry_checks:samples,wrong_grade_cells:wrongGradeCells};
            }""")
            assert geometry["wrong_grade_cells"] == 0, geometry
            page.goto(url + "?angle=45&hand=R&pitch=FF")
            page.wait_for_selector(".expected-50")
            before = page.locator(".expected-50").get_attribute("transform")
            page.locator("#angle").focus(); page.keyboard.press("ArrowRight")
            assert page.locator("#angle").input_value() == "46"
            assert page.locator(".expected-50").get_attribute("transform") != before
            page.locator("#play").click()
            page.wait_for_function("document.querySelector('#angle').value !== '46'")
            page.locator("#angle").focus(); page.keyboard.press("ArrowLeft")
            assert page.locator("#play").get_attribute("aria-pressed") == "false"
            page.goto(url + "?angle=45&hand=R&pitch=FF")
            page.wait_for_selector(".expected-50")
            expected = data["pitches"]["FF"]["hands"]["R"]["profiles"][105]["expected"]
            page.locator("#compare-hb").fill("-10.0"); page.locator("#compare-ivb").fill("16.0")
            assert abs(float(page.locator("#delta-status").get_attribute("data-delta-hb"))-(-10+expected["center"][0])) < 1e-6
            assert abs(float(page.locator("#delta-status").get_attribute("data-delta-ivb"))-(16-expected["center"][1])) < 1e-6
            page.locator("#compare-hb").fill("")
            assert page.locator(".comparison-point").count() == 0
            page.locator("#compare-hb").fill("-10")
            suffix = "public" if remote else "local"
            page.screenshot(path=str(output / f"preview-{suffix}-expected.png"), full_page=True)
            page.locator("#view").select_option("whiff")
            page.locator('[data-pitch="ST"]').click()
            if data["pitches"]["ST"]["validation"] is None:
                assert "시간 검증 표본 부족" in page.locator("#sample-status").inner_text()
            for code in ["FC", "CH"]:
                v=data["pitches"][code]["validation"]
                if v["movement"]["log_loss"] >= v["controls_only"]["log_loss"]:
                    page.locator(f'[data-pitch="{code}"]').click()
                    assert "예측 개선 미확인" in page.locator("#sample-status").inner_text()
            page.locator('[data-pitch="FF"]').click()
            page.screenshot(path=str(output / f"preview-{suffix}-whiff.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile page overflows"
            page.screenshot(path=str(output / f"preview-{suffix}-mobile.png"), full_page=True)
            page.goto(url + "?angle=999&hand=L&pitch=invalid")
            page.wait_for_selector("#angle:not([disabled])")
            assert int(page.locator("#angle").input_value()) == data["angle_max"]
            page.goto(url + "?thumb=1&angle=45&hand=L&pitch=FF")
            page.wait_for_selector('[data-thumbnail-ready="true"]')
            page.route("**/data/movement_zones/profiles.json*", lambda route: route.fulfill(status=404, body="missing"))
            page.goto(url)
            page.wait_for_function("document.querySelector('#sample-status').textContent.includes('HTTP 404')")
            for selector in ["#angle", "#play", "#view", "#compare-hb", "#compare-ivb"]:
                assert page.locator(selector).is_disabled()
            assert not errors, errors
            browser.close()
    finally:
        if server:
            server.shutdown(); server.server_close()
    evidence = {"url": url, "seasons": data["seasons"], "shape_pitches": data["shape_pitches"],
                "swings": data["swings"], "trackman_swings": data["trackman_swings"],
                "profiles_checked_in_browser": checked, "supported_whiff_profiles": supported,
                "supported_expected_profiles": expected_supported, **geometry,
                "holdout": {code: {"whiff": pitch["validation"], "shape": pitch["shape_validation"]} for code, pitch in data["pitches"].items()}}
    (output / ("validation-public.json" if remote else "validation.json")).write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in evidence.items() if k != "holdout"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url")
    main(parser.parse_args().url)
