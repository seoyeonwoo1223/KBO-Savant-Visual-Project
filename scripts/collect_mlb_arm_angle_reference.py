"""Collect public Savant shoulder/ball observations and official MLB heights.

Run from the checkout with PYTHONPATH=src. Seasonal aggregates are reference
observations, not video-labelled KBO pitches. Cached pages avoid repeated reads.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import gzip
import hashlib
import html
import json
from pathlib import Path
import re
import time

import numpy as np
import pandas as pd
import requests


def get_page(url, cache):
    if cache.exists():
        content = gzip.decompress(cache.read_bytes())
        return content, url
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(gzip.compress(response.content, mtime=0))
    time.sleep(.5)
    return response.content, response.url


def parse_height(page, player_id, final_url):
    # MLB's canonical redirect must retain the requested numeric identity.
    if not re.search(r"(?:/|-)"+re.escape(str(player_id))+r"(?:$|\?)", final_url):
        raise ValueError("MLB profile redirected to a different identity")
    text = page.decode("utf-8")
    field = re.search(r'<li[^>]*class="[^"]*player-header--vitals-height[^"]*"[^>]*>(.*?)</li>', text, re.S)
    if not field:
        raise ValueError("No labelled MLB height")
    match = re.search(r"(\d+)\s*'\s*(\d+)\s*\"", html.unescape(field[1]))
    if not match or not 0 <= int(match[2]) <= 11:
        raise ValueError("Unrecognized feet/inches height")
    height = (12*int(match[1])+int(match[2]))*2.54
    if not 140 <= height <= 220:
        raise ValueError("Implausible MLB height")
    return height


def collect(out, years):
    cache = out / "source_cache/mlb"
    out.mkdir(parents=True, exist_ok=True)
    observations, sources = [], []
    for year in years:
        url = f"https://baseballsavant.mlb.com/leaderboard/pitcher-arm-angles?season={year}"
        content, final_url = get_page(url, cache / f"savant-{year}.html.gz")
        text = content.decode("utf-8")
        if "throwing shoulder" not in text or "perfectly horizontal" not in text:
            raise ValueError("Savant page does not contain the expected arm-angle definition")
        matched = re.search(r"const rawData\s*=\s*(\[.*?\]);", text, re.S)
        if not matched:
            raise ValueError("Savant reference schema changed")
        data = pd.DataFrame(json.loads(matched[1]))
        if data.empty or data.pitcher.duplicated().any():
            raise ValueError("Savant pitcher-season reference must be nonempty and unique")
        # Confirm server-side selection; ?year= is ignored by this leaderboard.
        if not re.search(r'id="season-'+str(year)+r'"\s+name="season-'+str(year)+r'"\s+value="'+str(year)+r'"\s+checked', text):
            raise ValueError("Requested season is not selected in the returned reference page")
        data["season"] = year
        data["reference_source_url"] = url
        data["reference_source_sha256"] = hashlib.sha256(content).hexdigest()
        data["source_collected_at"] = datetime.now(timezone.utc).isoformat()
        observations.append(data)
        sources.append({"season": year, "url": url, "sha256": hashlib.sha256(content).hexdigest(), "rows": len(data)})
    data = pd.concat(observations, ignore_index=True)
    ids = sorted(data.pitcher.astype(str).unique())
    heights_path = out / "mlb_heights.csv"
    existing = pd.read_csv(heights_path, dtype={"pitcher": str}) if heights_path.exists() else pd.DataFrame()
    heights = existing.to_dict("records")
    known = set(existing.pitcher) if len(existing) else set()

    def profile(player_id):
        url = f"https://www.mlb.com/player/{player_id}"
        try:
            content, final_url = get_page(url, cache / f"player-{player_id}.html.gz")
            return {"pitcher": player_id, "height_cm": parse_height(content, player_id, final_url),
                    "height_source_url": url, "height_source_sha256": hashlib.sha256(content).hexdigest(),
                    "height_collected_at": datetime.now(timezone.utc).isoformat()}, None
        except (requests.RequestException, ValueError) as error:
            return None, {"pitcher": player_id, "error_type": type(error).__name__}

    errors = []
    pending = [value for value in ids if value not in known]
    with ThreadPoolExecutor(max_workers=3) as executor:
        for count, (height, error) in enumerate(executor.map(profile, pending), 1):
            if height:
                heights.append(height)
                pd.DataFrame(heights).to_csv(heights_path, index=False)
            if error:
                errors.append(error)
            if count % 30 == 0:
                print(f"MLB profiles processed {count}/{len(pending)}; heights {len(heights)}", flush=True)
    if not heights:
        raise RuntimeError("No verified MLB heights could be collected")
    data["pitcher"] = data.pitcher.astype(str)
    height_frame = pd.DataFrame(heights)
    if height_frame.pitcher.duplicated().any():
        raise ValueError("Duplicate MLB height IDs")
    data = data.merge(height_frame, on="pitcher", how="left", validate="many_to_one")
    data["rel_height_m"] = pd.to_numeric(data.release_ball_z)*.3048
    # The sources' horizontal sign conventions are opposite.
    data["rel_side_m"] = -pd.to_numeric(data.release_ball_x)*.3048
    data["shoulder_side_m"] = -(pd.to_numeric(data.release_ball_x)-pd.to_numeric(data.relative_release_ball_x)+pd.to_numeric(data.relative_shoulder_x))*.3048
    data["shoulder_height_m"] = pd.to_numeric(data.shoulder_z)*.3048
    data["reference_frontal_from_mean_points_deg"] = np.degrees(np.arctan2(data.rel_height_m-data.shoulder_height_m,
                                                                        np.abs(data.rel_side_m-data.shoulder_side_m)))
    data.to_csv(out / "mlb_reference.csv", index=False)
    metadata = {"source": "Official Savant pitcher arm angle leaderboard; default qualified selection",
                "definition_status": "verified_horizontal_throwing_shoulder_to_ball_at_release",
                "grain": "pitcher-season averages; mean angle is not angle of mean coordinates",
                "seasons": years, "sources": sources, "rows": len(data), "pitchers": len(ids),
                "height_players": len(heights), "missing_height_rows": int(data.height_cm.isna().sum()),
                "height_errors": errors, "datum": "Savant displayed ball and shoulder coordinates in feet; converted to metres",
                "nonlinear_aggregation_median_abs_difference_deg": float((data.arm_angle-data.reference_frontal_from_mean_points_deg).abs().median())}
    (out / "mlb_sources.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({k: metadata[k] for k in ("rows", "pitchers", "height_players", "missing_height_rows")}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path(".cache/arm_angle"))
    parser.add_argument("--seasons", nargs="+", type=int, default=[2020, 2021, 2022, 2023, 2024])
    args = parser.parse_args()
    collect(args.out, args.seasons)


if __name__ == "__main__":
    main()
