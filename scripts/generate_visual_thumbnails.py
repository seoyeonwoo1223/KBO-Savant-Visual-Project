"""Capture the configured KBO visual cards as deterministic WebP thumbnails.

Run from the repository root with:
    python scripts/generate_visual_thumbnails.py

Install the one browser runtime once after installing requirements:
    python -m playwright install chromium
"""
from __future__ import annotations

import argparse
import io
import json
import threading
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

from serve_web import Handler, WEB_ROOT


ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(__file__).with_name("visual_thumbnails.json")
CAPTURE_STYLE = """
*, *::before, *::after { animation: none !important; transition: none !important; caret-color: transparent !important; }
html { scroll-behavior: auto !important; }
"""


def load_config() -> dict:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    stage = config["stage"]
    assert stage["width"] == stage["height"] == 600
    assert stage["device_scale_factor"] == 2
    assert len(config["thumbnails"]) == 6
    return config


def start_server() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(WEB_ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def capture(config: dict, base_url: str) -> None:
    stage = config["stage"]
    expected_size = (stage["width"] * stage["device_scale_factor"], stage["height"] * stage["device_scale_factor"])
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={"width": stage["width"], "height": stage["height"]},
            device_scale_factor=stage["device_scale_factor"],
        )
        page = context.new_page()
        try:
            for thumbnail in config["thumbnails"]:
                page.goto(f"{base_url}{thumbnail['url']}", wait_until="networkidle")
                page.add_style_tag(content=CAPTURE_STYLE)
                page.wait_for_function(
                    "selector => document.querySelector(selector)?.dataset.thumbnailReady === 'true'",
                    arg=thumbnail["selector"],
                )
                page.evaluate("async () => { await document.fonts.ready; }")
                locator = page.locator(thumbnail["selector"])
                box = locator.bounding_box()
                assert box and round(box["width"]) == stage["width"] and round(box["height"]) == stage["height"]
                image = Image.open(io.BytesIO(locator.screenshot(animations="disabled"))).convert("RGB")
                if image.size != expected_size:
                    image = image.resize(expected_size, Image.Resampling.LANCZOS)
                assert image.size == expected_size
                output = ROOT / thumbnail["output"]
                output.parent.mkdir(parents=True, exist_ok=True)
                image.save(output, "WEBP", quality=stage["webp_quality"], method=6)
                with Image.open(output) as saved:
                    assert saved.format == "WEBP" and saved.size == expected_size
                print(f"{thumbnail['id']}: {output.relative_to(ROOT)} {expected_size[0]}x{expected_size[1]}")
        finally:
            context.close()
            browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", help="reuse an already-running static viewer")
    args = parser.parse_args()
    config = load_config()
    server = None
    try:
        if args.base_url:
            base_url = args.base_url.rstrip("/")
        else:
            server, base_url = start_server()
        capture(config, base_url)
    finally:
        if server:
            server.shutdown()
            server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
