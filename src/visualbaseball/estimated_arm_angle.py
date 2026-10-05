"""Frozen eAA inference on canonical season pitches, without retraining or web inputs.

The public entry point prefers the latest frozen numerical model and retains v1 for
insufficient fastball samples. Bounds are model references, not measured KBO
confidence intervals; v1 withholds bounds for unseen stadiums.
"""
from __future__ import annotations

from collections import defaultdict
import csv
import json
from pathlib import Path
import re
import unicodedata

import numpy as np
import pyarrow.parquet as pq

from .curated import _number

MODEL_PATH = "data/models/estimated_arm_angle_v1.json"
HEIGHT_PATH = "data/tracking/player_heights.csv"


def _name(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", str(value or "")))


def _heights(root):
    path = root / HEIGHT_PATH
    if not path.exists():
        return {}
    result = {}
    with path.open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            player_id = row["player_id"]
            height = _number(row["height_cm"])
            if player_id in result:
                raise ValueError("Duplicate verified height player ID")
            if (height is None or not 140 <= height <= 220 or not row["source_url"].startswith("https://")
                    or not re.fullmatch(r"[0-9a-f]{64}", row["source_sha256"])):
                raise ValueError("Invalid verified height or source provenance")
            result[player_id] = row
    return result


def _predict(model, x):
    values = np.asarray(x, dtype=float)
    if "polynomial_powers" in model:
        values = np.prod(values ** np.asarray(model["polynomial_powers"]), axis=1)
    standardized = (values-np.asarray(model["standardization_mean"]))/np.asarray(model["standardization_scale"])
    return np.asarray(model["ridge_coefficients"]) @ standardized + np.asarray(model["intercept"])


def _outside(model, x):
    return bool(np.any(np.asarray(x) < np.asarray(model["training_feature_min"]))
                or np.any(np.asarray(x) > np.asarray(model["training_feature_max"])))


def _empty(status, count=0, total=0):
    return {"model_id": "eAA-v1", "scope": "pitcher_season", "angle_deg": None,
            "status": status, "n": count, "total_pitches": total,
            "range": {"kind": "model_reference_KBO_coverage_unknown", "status": "withheld_estimate",
                      "low_deg": None, "high_deg": None}, "flags": {}}


def _season_estimates_v1(root: Path, season: int, rows: list[dict]) -> dict[str, dict]:
    """Use every valid canonical release, independently of pitch display grouping.

    Averaging each pitch's velocity ratio preserves the linear release bridge.
    Applying the nonlinear angle model happens only after seasonal aggregation.
    """
    model_path = root / MODEL_PATH
    model = json.loads(model_path.read_text(encoding="utf-8")) if model_path.exists() else None
    if model and (model.get("schema_version") != 1 or model.get("model_id") != "eAA-v1"):
        raise ValueError("Unsupported frozen eAA model")
    bio_path = root / "data/curated/players/player_bio.parquet"
    bio = ({str(p["player_id"]): p for p in pq.read_table(bio_path, columns=["player_id", "player_name", "throws"]).to_pylist()}
           if bio_path.exists() else {})
    heights = _heights(root)
    grouped = defaultdict(lambda: {"total": 0, "features": [], "stadiums": set(), "plane55": False})
    for row in rows:
        if row.get("season") != season or not row.get("pitcher_id"):
            continue
        player_id = str(row["pitcher_id"])
        bucket = grouped[player_id]
        bucket["total"] += 1
        player, height_row = bio.get(player_id), heights.get(player_id)
        if not player or not height_row:
            continue
        if not (_name(player["player_name"]) == _name(height_row["player_name"]) == _name(row.get("pitcher_name"))):
            continue
        sign = {"R": 1., "L": -1.}.get(player.get("throws"))
        if sign is None:
            continue
        x, z, vx, vy, vz = [_number(row.get(c)) for c in ("release_x_55", "release_z_55", "vx_55", "vy_55", "vz_55")]
        if (not row.get("trajectory_valid") or None in (x, z, vx, vy, vz)
                or not -200 <= x <= 200 or not 5 <= z <= 270 or vy >= 0):
            continue
        h = float(height_row["height_cm"])/100
        feature = [h, -sign*x/100, z/100, -sign*vx/vy, vz/vy]
        if not np.isfinite(feature).all():
            continue
        bucket["features"].append(feature)
        bucket["stadiums"].add(str(row.get("stadium") or ""))
        bucket["plane55"] |= row.get("source_y0") == 55
    output = {}
    for player_id, bucket in grouped.items():
        n, total = len(bucket["features"]), bucket["total"]
        player, height_row = bio.get(player_id), heights.get(player_id)
        status = "withheld_invalid_release"
        if model is None:
            status = "unavailable_model"
        elif not player or not height_row:
            status = "withheld_missing_verified_height"
        elif _name(player["player_name"]) != _name(height_row["player_name"]):
            status = "withheld_height_identity_mismatch"
        elif player.get("throws") not in ("R", "L"):
            status = "withheld_missing_hand"
        elif n < model["minimum_pitches"]:
            status = "withheld_small_sample"
        payload = _empty(status, n, total)
        if n and model:
            mean = np.mean(bucket["features"], axis=0)
            correction = _predict(model["bridge"], mean)
            h, arm_x, z = mean[:3]
            angle_x = [h, (z+correction[1])/h, (arm_x+correction[0])/h, float(player["throws"] == "L")]
            outside_bridge, outside_angle = _outside(model["bridge"], mean), _outside(model["angle"], angle_x)
            raw_angle = float(_predict(model["angle"], angle_x))
            payload["flags"] = {"unseen_stadium": bool(bucket["stadiums"]-set(model["bridge"]["known_stadiums"])),
                                "future_season": season > max(model["bridge"]["training_seasons"])+1,
                                "source_plane_55_present": bool(bucket["plane55"]),
                                "outside_bridge_training_range": outside_bridge, "outside_MLB_training_range": outside_angle}
            # Use the same domain priority as the research implementation.
            if outside_angle:
                payload["status"] = "withheld_MLB_extrapolation"
            elif outside_bridge:
                payload["status"] = "withheld_bridge_extrapolation"
            elif n >= model["minimum_pitches"] and abs(raw_angle) <= 90:
                payload["status"] = "estimated_KBO_angle_unvalidated"
                payload["angle_deg"] = round(raw_angle, 4)
                payload["height_cm"] = float(height_row["height_cm"])
                radius = model["range"]["total_radius_deg"]
                unseen = payload["flags"]["unseen_stadium"]
                payload["range"] = {"kind": "model_reference_KBO_coverage_unknown",
                                    "status": "unavailable_unseen_stadium_bias" if unseen else (
                                        "reference_only_future_season_unvalidated" if payload["flags"]["future_season"] else "reference_only_KBO_angle_unvalidated"),
                                    "low_deg": None if unseen else round(max(-90., raw_angle-radius), 4),
                                    "high_deg": None if unseen else round(min(90., raw_angle+radius), 4)}
            elif n >= model["minimum_pitches"]:
                payload["status"] = "withheld_invalid_prediction"
        output[player_id] = payload
    return output


def season_estimates(root: Path, season: int, rows: list[dict]) -> dict[str, dict]:
    """One season estimate, preferring the frozen numeric model when available."""
    fallback = _season_estimates_v1(root, season, rows)
    from .estimated_arm_angle_numeric import MODEL_PATH as NUMERIC_MODEL_PATH, ROBUST_MODEL_PATH, season_estimates_numeric
    if (root/NUMERIC_MODEL_PATH).exists() or (root/ROBUST_MODEL_PATH).exists():
        return season_estimates_numeric(root,season,rows,fallback)
    return fallback
