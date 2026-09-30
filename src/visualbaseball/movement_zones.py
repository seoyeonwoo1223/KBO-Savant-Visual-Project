"""One-degree, outcome-based movement profiles from deduplicated VB/TrackMan pitches.

The angle is a release-slot proxy, NOT a measured shoulder-to-ball arm angle.
TrackMan movement is preferred on safely matched pitches; corrected VB movement
is mapped to that scale on the remaining pitches. No original data is rewritten.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .curated import file_sha256, load_table, source_sha256, value_sha256
from .movement_calibration import calibrate
from .pitch_arsenal import _load_batter_hands, _pitch_code, _resolved_batter_stance

ANGLE_MIN, ANGLE_MAX = -60, 85
SHOULDER_HEIGHT_CM = 130.0
WINDOW_DEG, MIN_SWINGS, MIN_PITCHERS = 5, 150, 5
PITCH_NAMES = {"FF": "4-Seam", "SI": "Sinker / 2-Seam", "FC": "Cutter",
               "SL": "Slider", "ST": "Sweeper", "CU": "Curveball", "CH": "Changeup", "FS": "Splitter / Fork"}
COLUMNS = ["season", "game_id", "pitch_id", "pitcher_id", "batter_id", "pitch_type_code", "pitch_type_kr",
           "parse_status", "trajectory_valid", "release_x_50", "release_x_55", "release_z_55", "stadium",
           "horizontal_movement_cm", "vertical_movement_cm", "velocity_kmh", "px", "pz",
           "sz_top", "sz_bottom", "balls_before", "strikes_before", "batter_stance", "is_swing", "is_contact"]


def release_angle(x, z, shoulder_height_cm=SHOULDER_HEIGHT_CM):
    return np.degrees(np.arctan2(np.asarray(z) - shoulder_height_cm, np.abs(np.asarray(x))))


def _mapping(vb, tm):
    """Robust affine VB -> TM mapping, independently estimated for each component."""
    ok = np.isfinite(vb) & np.isfinite(tm)
    x, y = np.asarray(vb)[ok], np.asarray(tm)[ok]
    if len(x) < 100 or np.std(x) < 1:
        raise ValueError("Insufficient matched movement for TrackMan scale calibration")
    keep = np.ones(len(x), dtype=bool)
    for _ in range(2):
        intercept, slope = np.linalg.lstsq(np.column_stack([np.ones(keep.sum()), x[keep]]), y[keep], rcond=None)[0]
        residual = y - intercept - slope * x
        mad = 1.4826 * np.median(np.abs(residual - np.median(residual)))
        if mad > 0:
            keep = np.abs(residual - np.median(residual)) <= 4 * mad
    return {"intercept_cm": float(intercept), "slope": float(slope), "n": int(keep.sum()),
            "rmse_cm": float(np.sqrt(np.mean(residual[keep] ** 2)))}


def _prepare(root, season, recent_mappings):
    frame = load_table(root, "pitches", season, columns=COLUMNS).to_pandas()
    if frame.pitch_id.duplicated().any():
        raise ValueError(f"Duplicate canonical pitch IDs in {season}")
    tm_path = root / f"data/tracking/raw/season={season}/trackman_history.csv"
    match_path = root / "analysis/movement_calibration/match_trackman.py"
    provenance = {"season": season, "vb_pitches": len(frame),
                  "vb_sha256": value_sha256(pd.util.hash_pandas_object(frame, index=False).astype(str).tolist()),
                  "trackman_sha256": file_sha256(tm_path) if tm_path.exists() else None,
                  "crosswalk_sha256": file_sha256(root / "data/tracking/player_id_crosswalk.json"),
                  "player_bio_sha256": file_sha256(root / "data/curated/players/player_bio.parquet"),
                  "code_sha256": {p.name: source_sha256(p) for p in [Path(__file__), Path(__file__).with_name("movement_calibration.py"),
                                   Path(__file__).with_name("pitch_arsenal.py"), match_path, root / "scripts/build_trackman_id_crosswalk.py"]},
                  "recent_mappings": recent_mappings if not tm_path.exists() else None}
    signature = value_sha256(provenance)
    cache = root / f".cache/movement_zones/{season}-{signature}.parquet"
    if cache.exists():
        return pd.read_parquet(cache), json.loads(cache.with_suffix(".json").read_text(encoding="utf-8"))
    codes = [_pitch_code(row) for row in frame[["pitch_id", "pitch_type_code", "pitch_type_kr"]].to_dict("records")]
    frame["code"] = pd.Series(codes, index=frame.index).replace({"FT": "SI"})
    frame[["hb", "ivb"]] = np.asarray(calibrate(frame.to_dict("records"), codes), dtype=float)
    pitcher_x = frame.groupby("pitcher_id").release_x_55.transform("median")
    frame["hand"] = np.where(pitcher_x < 0, "R", "L")
    missing_stance = ~frame.batter_stance.isin(["R", "L"])
    batter_hands = _load_batter_hands(root, season)
    frame.loc[missing_stance, "batter_stance"] = [_resolved_batter_stance(row, batter_hands)
        for row in frame.loc[missing_stance, ["batter_id", "batter_stance", "release_x_50"]].to_dict("records")]
    frame["tm"] = False
    mappings = {}
    if tm_path.exists():
        spec = importlib.util.spec_from_file_location("movement_match", match_path)
        matcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(matcher)
        matched, match_meta = matcher.match_season(root, season, 3.0)
        if matched.pitch_id.duplicated().any():
            raise ValueError(f"Multiple TrackMan matches for one VB pitch in {season}")
        matched = matched.set_index("pitch_id").reindex(frame.pitch_id)
        tm_stance = matched.batter_hand.map({"Right": "R", "Left": "L"}).to_numpy()
        unknown = ~frame.batter_stance.isin(["R", "L"]) & pd.notna(tm_stance)
        frame.loc[unknown, "batter_stance"] = tm_stance[unknown]
        targets = {"hb": -pd.to_numeric(matched.horz_break, errors="coerce").to_numpy(),
                   "ivb": pd.to_numeric(matched.induced_vert_break, errors="coerce").to_numpy()}
        mappings = {hand: {key: _mapping(frame.loc[frame.hand == hand, key].to_numpy(), target[frame.hand == hand])
                           for key, target in targets.items()} for hand in ("R", "L")}
        provenance["matching"] = match_meta
    else:
        if not recent_mappings:
            raise ValueError("TrackMan calibration must be built before VB-only seasons")
        mappings = recent_mappings
        targets = {key: np.full(len(frame), np.nan) for key in ("hb", "ivb")}
    for hand in ("R", "L"):
        mask = frame.hand == hand
        for key in ("hb", "ivb"):
            fit = mappings[hand][key]
            frame.loc[mask, key] = fit["intercept_cm"] + fit["slope"] * frame.loc[mask, key]
    paired = np.isfinite(targets["hb"]) & np.isfinite(targets["ivb"])
    frame.loc[paired, ["hb", "ivb"]] = np.column_stack([targets["hb"][paired], targets["ivb"][paired]])
    frame.loc[paired, "tm"] = True
    frame["angle"] = release_angle(frame.release_x_55, frame.release_z_55)
    frame["hb"] *= np.where(frame.hand == "R", -1, 1) / 2.54  # arm-side-positive inches
    frame["ivb"] /= 2.54
    frame["z"] = (frame.pz - (frame.sz_top + frame.sz_bottom) / 2) / ((frame.sz_top - frame.sz_bottom) / 2)
    frame["opposite"] = ((frame.batter_stance == "R") & (frame.hand == "L")) | ((frame.batter_stance == "L") & (frame.hand == "R"))
    needed = ["angle", "hb", "ivb", "velocity_kmh", "px", "z", "balls_before", "strikes_before"]
    checks = {"not_swing_or_unknown_contact": frame.is_swing.eq(True) & frame.is_contact.isin([True, False]),
              "invalid_parse_or_trajectory": (frame.parse_status == "ok") & frame.trajectory_valid.eq(True),
              "unknown_pitch_type": frame.code.isin(PITCH_NAMES),
              "missing_inputs_or_stance": frame[needed].apply(np.isfinite).all(axis=1) & frame.batter_stance.isin(["R", "L"]),
              "outside_model_domain": frame.angle.between(ANGLE_MIN, ANGLE_MAX) & frame.hb.between(-30, 30) & frame.ivb.between(-25, 30)
                  & frame.velocity_kmh.between(70, 175) & frame.balls_before.between(0, 3) & frame.strikes_before.between(0, 2)}
    valid = pd.Series(True, index=frame.index)
    provenance["exclusion_counts"] = {}
    for reason, check in checks.items():
        provenance["exclusion_counts"][reason] = int((valid & ~check).sum())
        valid &= check
    provenance["resolved_batter_stances"] = int((missing_stance & frame.batter_stance.isin(["R", "L"])).sum())
    frame = frame[valid].copy()
    frame["whiff"] = ~frame.is_contact.astype(bool)
    provenance.update({"eligible_swings": len(frame), "trackman_swings": int(frame.tm.sum()),
                       "excluded_pitches": provenance["vb_pitches"] - len(frame), "mapping": mappings})
    cache.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(cache, index=False)
    cache.with_suffix(".json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    return frame, provenance


def design(frame, movement=True):
    a, h, v = (frame[key].to_numpy(float) / scale for key, scale in [("angle", 45), ("hb", 15), ("ivb", 15)])
    x, z = frame.px.to_numpy(float), frame.z.to_numpy(float)
    control = np.column_stack([(frame.velocity_kmh.to_numpy(float) - 140) / 10, x, z, x*x, z*z,
                               frame.balls_before, frame.strikes_before, frame.opposite,
                               frame.hand.eq("L"), (frame.season - 2022) / 4, frame.tm])
    return np.column_stack([a, h, v, a*a, h*h, v*v, a*h, a*v, h*v, control]) if movement else control


def fit_model(frame, movement=True):
    return make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=500, tol=1e-6)).fit(design(frame, movement), frame.whiff)


def _scores(y, p):
    return {"log_loss": float(log_loss(y, p)), "brier": float(brier_score_loss(y, p)), "auc": float(roc_auc_score(y, p))}


def profiles(frame, model):
    """Smoothed observed support, ranked by a standardized regression probability."""
    hb, ivb = np.meshgrid(np.arange(-30, 31), np.arange(-25, 31), indexing="ij")
    points = np.column_stack([hb.ravel(), ivb.ravel()])
    result = {}
    for hand in ("R", "L"):
        sample = frame[frame.hand == hand]
        density, _ = np.histogramdd(sample[["angle", "hb", "ivb"]].to_numpy(float), bins=[np.arange(ANGLE_MIN-.5, ANGLE_MAX+1.5),
                                                                 np.arange(-30.5, 31.5), np.arange(-25.5, 31.5)])
        density = gaussian_filter(density, sigma=[WINDOW_DEG, 1, 1], mode="constant")
        reference = pd.DataFrame({"angle": 0., "hb": points[:, 0], "ivb": points[:, 1], "px": 0., "z": 0.,
                                  "velocity_kmh": float(sample.velocity_kmh.median()) if len(sample) else float(frame.velocity_kmh.median()),
                                  "balls_before": 1, "strikes_before": 1, "opposite": .5, "hand": hand,
                                  "season": int(frame.season.max()), "tm": False})
        slices = []
        for angle in range(ANGLE_MIN, ANGLE_MAX + 1):
            local = sample[(sample.angle - angle).abs() <= WINDOW_DEG]
            item = {"angle": angle, "swings": len(local), "pitchers": int(local.pitcher_id.nunique()), "zones": None}
            if len(local) >= MIN_SWINGS and item["pitchers"] >= MIN_PITCHERS:
                reference["angle"] = angle
                probability = model.predict_proba(design(reference))[:, 1]
                weight = density[angle - ANGLE_MIN].ravel().copy()
                weight[weight < weight.max() * .05] = 0  # no contours over unsupported movement
                order = np.argsort(probability)
                quantile = np.empty(len(weight))
                quantile[order] = (np.cumsum(weight[order]) - weight[order] / 2) / weight.sum()
                masks = {"dead": quantile <= .25, "average": (quantile > .25) & (quantile < .75), "elite": quantile >= .75}
                zones = {}
                for key, mask in masks.items():
                    w = weight * mask
                    if w.sum() == 0:
                        raise ValueError(f"No supported {key} distribution at {hand}/{angle}")
                    center = np.average(points, axis=0, weights=w)
                    delta = points - center
                    covariance = (delta * w[:, None]).T @ delta / w.sum()
                    # ponytail: Gaussian 75% ellipses summarize irregular ranked regions; use contours if shape detail is needed.
                    radius = np.sqrt(-2 * np.log(.25) * np.diag(covariance))
                    zones[key] = {"center": center.round(4).tolist(), "covariance": covariance.round(4).tolist(),
                                  "hb": [round(float(center[0] - radius[0]), 3), round(float(center[0] + radius[0]), 3)],
                                  "ivb": [round(float(center[1] - radius[1]), 3), round(float(center[1] + radius[1]), 3)],
                                  "whiff_pct": round(float(np.average(probability, weights=w) * 100), 2)}
                item["zones"] = zones
            slices.append(item)
        result[hand] = {"velocity_kmh": reference.velocity_kmh.iloc[0], "profiles": slices}
    return result


def build_movement_zones(root: Path):
    seasons = sorted(int(path.name.split("=")[1]) for path in (root / "data/curated/pitches").glob("season=*"))
    frames, sources, recent = [], [], []
    for season in seasons:
        mappings = {hand: {key: {field: float(np.average([m[hand][key][field] for m in recent],
                                                           weights=[m[hand][key]["n"] for m in recent]))
                                 for field in ("intercept_cm", "slope")}
                          for key in ("hb", "ivb")} for hand in ("R", "L")} if recent else None
        frame, source = _prepare(root, season, mappings)
        frames.append(frame); sources.append(source)
        if season >= 2022 and source["trackman_sha256"]:
            recent.append(source["mapping"])
        print(f"movement zones {season}: {len(frame):,} swings, {source['trackman_swings']:,} TrackMan", flush=True)
    frame = pd.concat(frames, ignore_index=True)
    if frame.pitch_id.duplicated().any():
        raise ValueError("Duplicate pitch IDs across seasons")
    pitches = {}
    for code, name in PITCH_NAMES.items():
        sample = frame[frame.code == code]
        if len(sample) < 1000 or sample.whiff.nunique() != 2:
            continue
        train, test = sample[sample.season < seasons[-1]], sample[sample.season == seasons[-1]]
        validation = None
        if len(train) >= 1000 and len(test) >= 100 and train.whiff.nunique() == test.whiff.nunique() == 2:
            full, baseline = fit_model(train), fit_model(train, False)
            validation = {"train_through": seasons[-2], "test_season": seasons[-1], "test_swings": len(test),
                          "movement": _scores(test.whiff, full.predict_proba(design(test))[:, 1]),
                          "controls_only": _scores(test.whiff, baseline.predict_proba(design(test, False))[:, 1])}
        model = fit_model(sample)
        pitches[code] = {"name": name, "swings": len(sample), "validation": validation,
                         "model": {"intercept": model[-1].intercept_.tolist(), "coefficients": model[-1].coef_.tolist(),
                                   "mean": model[0].mean_.tolist(), "scale": model[0].scale_.tolist()},
                         "hands": profiles(sample, model)}
        print(f"movement zones {code}: fitted {len(sample):,} swings", flush=True)
    artifact = {"schema_version": 1, "angle_min": ANGLE_MIN, "angle_max": ANGLE_MAX, "step": 1,
                "shoulder_height_cm": SHOULDER_HEIGHT_CM, "window_deg": WINDOW_DEG,
                "min_swings": MIN_SWINGS, "min_pitchers": MIN_PITCHERS, "seasons": seasons,
                "swings": len(frame), "trackman_swings": int(frame.tm.sum()), "sources": sources,
                "angle_definition": "atan2(release_z_55_cm - 130, abs(release_x_55_cm)); fixed reference shoulder, no measured shoulder",
                "outcome": "whiff / swings; standardized at plate center, 1-1 count, 50% opposite stance, hand-specific median velocity, latest season, VB source",
                "zone_definition": "elite: upper 25%, dead: lower 25%, average: middle 50% of model whiff probability over locally observed movement; approximate Gaussian 75% ellipses",
                "pitches": pitches}
    destination = root / "web/data/movement_zones/profiles.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(artifact, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return len(frame)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    build_movement_zones(args.root.resolve())
