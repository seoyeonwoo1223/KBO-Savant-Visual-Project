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
REFERENCE_TIME_S = .4
PLATE_Y_FT = 17 / 12
REFERENCES = [
    {"name": "Baseball Savant · movement", "url": "https://baseballsavant.mlb.com/pitch-movement",
     "use": "구속·릴리스 조건을 맞춘 비교와 IVB의 중력 제외 정의. MLB 계수는 사용하지 않음."},
    {"name": "Max Bay · Dynamic Dead Zone", "url": "https://dynamic-dead-zone.streamlit.app/",
     "use": "공개 Mathematical explainer의 조건부 다변량 정규 평균·공분산. 원본은 실측 팔각도·신장 대비 익스텐션 및 FF/SI/FC 혼합 모형."},
    {"name": "Alex Chamberlain · Pitch Leaderboard v8", "url": "https://public.tableau.com/app/profile/chamb117/viz/PitchLeaderboardv8/Dashboard",
     "use": "공개 workbook의 AxOE/AzOE: 실제 가속도 − 동일 구종·릴리스 방향의 기대 가속도. 릴리스 방향과 Delta 정의 참고."},
    {"name": "야구공작소 · ‘이것’ 없이는 무브먼트도 의미 없다", "url": "https://yagongso.com/이것-없이는-무브먼트도-의미-없다/",
     "use": "팔각도 대비 무브먼트와 체공 시간 보정의 맥락. 변화구 적용은 탐색적임."},
]
PITCH_NAMES = {"FF": "4-Seam", "SI": "Sinker / 2-Seam", "FC": "Cutter",
               "SL": "Slider", "ST": "Sweeper", "CU": "Curveball", "CH": "Changeup", "FS": "Splitter / Fork"}
COLUMNS = ["season", "game_id", "pitch_id", "pitcher_id", "batter_id", "pitch_type_code", "pitch_type_kr",
           "parse_status", "trajectory_valid", "release_x_50", "release_x_55", "release_z_55", "stadium",
           "horizontal_movement_cm", "vertical_movement_cm", "velocity_kmh", "px", "pz",
           "sz_top", "sz_bottom", "balls_before", "strikes_before", "batter_stance", "is_swing", "is_contact",
           "vx_55", "vy_55", "vz_55", "ay"]


def release_angle(x, z, shoulder_height_cm=SHOULDER_HEIGHT_CM):
    return np.degrees(np.arctan2(np.asarray(z) - shoulder_height_cm, np.abs(np.asarray(x))))


def travel_time(vy, ay, delta_y):
    """Stable near root of delta_y = vy*t + ay*t²/2, also valid backwards to release."""
    vy, ay, delta_y = np.broadcast_arrays(np.asarray(vy, float), np.asarray(ay, float), np.asarray(delta_y, float))
    discriminant = vy*vy + 2*ay*delta_y
    with np.errstate(invalid="ignore", divide="ignore"):
        time = 2*delta_y / (vy - np.sqrt(discriminant))
    return np.where((vy < 0) & (discriminant >= 0) & np.isfinite(time), time, np.nan)


def normalize_time(movement, flight):
    return np.asarray(movement) * (REFERENCE_TIME_S / np.asarray(flight)) ** 2


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
    extension = np.full(len(frame), np.nan)
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
        extension = matched.extension.to_numpy(float)  # metres in the stored TrackMan exports
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
    frame["hra"] = np.degrees(np.arctan2(frame.vx_55, -frame.vy_55)) * np.where(frame.hand == "R", -1, 1)
    frame["vra"] = np.degrees(np.arctan2(frame.vz_55, -frame.vy_55))
    frame["flight"] = travel_time(frame.vy_55, frame.ay, PLATE_Y_FT - 55)
    extended = paired & np.isfinite(extension) & (extension > .5) & (extension < 3)
    release_time = travel_time(frame.vy_55, frame.ay, 60.5 - extension / .3048 - 55)
    frame.loc[extended, "flight"] -= release_time[extended]
    raw_domain = frame.hb.between(-30, 30) & frame.ivb.between(-25, 30)
    frame["hb"] = normalize_time(frame.hb, frame.flight)
    frame["ivb"] = normalize_time(frame.ivb, frame.flight)
    frame["z"] = (frame.pz - (frame.sz_top + frame.sz_bottom) / 2) / ((frame.sz_top - frame.sz_bottom) / 2)
    frame["opposite"] = ((frame.batter_stance == "R") & (frame.hand == "L")) | ((frame.batter_stance == "L") & (frame.hand == "R"))
    needed = ["angle", "hb", "ivb", "velocity_kmh", "hra", "vra", "flight"]
    shape_checks = {"invalid_parse_or_trajectory": (frame.parse_status == "ok") & frame.trajectory_valid.eq(True),
              "unknown_pitch_type": frame.code.isin(PITCH_NAMES),
              "missing_shape_inputs": frame[needed].apply(np.isfinite).all(axis=1),
              "outside_model_domain": frame.angle.between(ANGLE_MIN, ANGLE_MAX) & frame.hb.between(-30, 30) & frame.ivb.between(-25, 30)
                  & raw_domain & frame.velocity_kmh.between(70, 175) & frame.flight.between(.25, .9)
                  & frame.hra.between(-15, 15) & frame.vra.between(-15, 15)}
    swing_checks = {"not_swing_or_unknown_contact": frame.is_swing.eq(True) & frame.is_contact.isin([True, False]),
                    **shape_checks, "missing_outcome_controls": frame[["px", "z", "balls_before", "strikes_before"]].apply(np.isfinite).all(axis=1)
                    & frame.batter_stance.isin(["R", "L"]) & frame.balls_before.between(0, 3) & frame.strikes_before.between(0, 2)}
    masks = {}
    for population, checks in [("shape", shape_checks), ("swing", swing_checks)]:
        valid = pd.Series(True, index=frame.index)
        counts = {}
        for reason, check in checks.items():
            counts[reason] = int((valid & ~check).sum())
            valid &= check
        provenance["shape_exclusion_counts" if population == "shape" else "exclusion_counts"] = counts
        masks[population] = valid
    frame["eligible_swing"] = masks["swing"]
    frame["whiff"] = np.where(masks["swing"], ~frame.is_contact.fillna(True).astype(bool), np.nan)
    provenance["resolved_batter_stances"] = int((missing_stance & frame.batter_stance.isin(["R", "L"])).sum())
    provenance.update({"eligible_swings": int(masks["swing"].sum()), "shape_pitches": int(masks["shape"].sum()),
                       "trackman_swings": int((masks["swing"] & frame.tm).sum()),
                       "trackman_shape_pitches": int((masks["shape"] & frame.tm).sum()),
                       "flight_from_trackman_extension": int((masks["shape"] & extended).sum()),
                       "excluded_pitches": provenance["vb_pitches"] - int(masks["swing"].sum()), "mapping": mappings})
    frame = frame.loc[masks["shape"], ["season", "pitch_id", "pitcher_id", "code", "hand", *needed,
                      "tm", "eligible_swing", "whiff", "px", "z", "balls_before", "strikes_before", "opposite"]].copy()
    cache.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(cache, index=False)
    cache.with_suffix(".json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    return frame, provenance


def release_features(frame):
    return frame[["angle", "hra", "vra", "flight"]].to_numpy(float) / [45, 5, 5, .4]


def fit_expectation(frame):
    """Conditional Gaussian: μm + Σmr Σrr⁺(r−μr), Σmm − Σmr Σrr⁺ Σrm."""
    if len(frame) < 2:
        return None
    release = release_features(frame)
    movement = frame[["hb", "ivb"]].to_numpy(float)
    joint = np.column_stack([movement, release])
    covariance = np.cov(joint, rowvar=False)
    beta = covariance[:2, 2:] @ np.linalg.pinv(covariance[2:, 2:], hermitian=True)
    conditional = covariance[:2, :2] - beta @ covariance[2:, :2]
    values, vectors = np.linalg.eigh((conditional + conditional.T) / 2)
    conditional = (vectors * np.maximum(values, 1e-6)) @ vectors.T  # numerical PSD floor only
    return {"movement_mean": movement.mean(axis=0).tolist(), "release_mean": release.mean(axis=0).tolist(),
            "coefficients": beta.tolist(), "covariance": conditional.tolist(),
            "unconditional_covariance": covariance[:2, :2].tolist(), "pitches": len(frame)}


def expected_movement(frame, model):
    return (release_features(frame) - model["release_mean"]) @ np.asarray(model["coefficients"]).T + model["movement_mean"]


def with_deltas(frame, models):
    frame = frame.copy()
    frame[["delta_hb", "delta_ivb"]] = np.nan
    for hand, model in models.items():
        mask = frame.hand == hand
        if model and mask.any():
            frame.loc[mask, ["delta_hb", "delta_ivb"]] = frame.loc[mask, ["hb", "ivb"]].to_numpy() - expected_movement(frame[mask], model)
    return frame[np.isfinite(frame[["delta_hb", "delta_ivb"]]).all(axis=1)]


def expectation_scores(frame, model):
    actual = frame[["hb", "ivb"]].to_numpy()
    residual = actual - expected_movement(frame, model)
    covariance = np.asarray(model["covariance"])
    distance = np.einsum("ij,jk,ik->i", residual, np.linalg.inv(covariance), residual)
    baseline = actual - model["movement_mean"]
    return {"test_pitches": len(frame), "rmse_hb": float(np.sqrt(np.mean(residual[:, 0]**2))),
            "rmse_ivb": float(np.sqrt(np.mean(residual[:, 1]**2))),
            "baseline_rmse_hb": float(np.sqrt(np.mean(baseline[:, 0]**2))),
            "baseline_rmse_ivb": float(np.sqrt(np.mean(baseline[:, 1]**2))),
            "coverage_50": float(np.mean(distance <= -2*np.log(.5))),
            "coverage_80": float(np.mean(distance <= -2*np.log(.2)))}


def design(frame, movement=True):
    a = frame.angle.to_numpy(float) / 45
    x, z = frame.px.to_numpy(float), frame.z.to_numpy(float)
    control = np.column_stack([(frame.velocity_kmh.to_numpy(float) - 140) / 10, x, z, x*x, z*z,
                               frame.balls_before, frame.strikes_before, frame.opposite,
                               frame.hand.eq("L"), (frame.season - 2022) / 4, frame.tm,
                               a, a*a, frame.hra/5, frame.vra/5, frame.flight/.4])
    if not movement:
        return control
    h, v = frame.delta_hb.to_numpy(float)/15, frame.delta_ivb.to_numpy(float)/15
    return np.column_stack([h, v, h*h, v*v, a*h, a*v, h*v, control])


def fit_model(frame, movement=True):
    return make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=500, tol=1e-6)).fit(design(frame, movement), frame.whiff)


def _scores(y, p):
    return {"log_loss": float(log_loss(y, p)), "brier": float(brier_score_loss(y, p)), "auc": float(roc_auc_score(y, p))}


def profiles(frame, model, expectations):
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
                                  "season": int(frame.season.max()), "tm": False, "hra": 0., "vra": 0., "flight": .4})
        slices = []
        for angle in range(ANGLE_MIN, ANGLE_MAX + 1):
            local = sample[(sample.angle - angle).abs() <= WINDOW_DEG]
            swings = local[local.eligible_swing]
            item = {"angle": angle, "swings": len(swings), "pitchers": int(swings.pitcher_id.nunique()),
                    "shape_pitches": len(local), "shape_pitchers": int(local.pitcher_id.nunique()), "expected": None, "zones": None}
            if len(local) >= MIN_SWINGS and item["shape_pitchers"] >= MIN_PITCHERS and expectations[hand]:
                reference["angle"] = angle
                context = np.average(local[["hra", "vra", "flight"]], axis=0, weights=np.exp(-.5*((local.angle-angle)/WINDOW_DEG)**2))
                reference[["hra", "vra", "flight"]] = context
                mean = expected_movement(reference.iloc[:1], expectations[hand])[0]
                item["expected"] = {"center": mean.round(4).tolist(), "covariance": expectations[hand]["covariance"],
                                    "hra": float(context[0]), "vra": float(context[1]), "flight": float(context[2])}
            if len(swings) >= MIN_SWINGS and item["pitchers"] >= MIN_PITCHERS and item["expected"]:
                reference[["delta_hb", "delta_ivb"]] = points - mean
                probability = model.predict_proba(design(reference))[:, 1]
                weight = density[angle - ANGLE_MIN].ravel().copy()
                weight[weight < weight.max() * .05] = 0  # no contours over unsupported movement
                order = np.argsort(probability)
                quantile = np.empty(len(weight))
                quantile[order] = (np.cumsum(weight[order]) - weight[order] / 2) / weight.sum()
                masks = {"low": (quantile <= .25) & (weight > 0), "average": (quantile > .25) & (quantile < .75) & (weight > 0),
                         "high": (quantile >= .75) & (weight > 0)}
                zones = {}
                for key, mask in masks.items():
                    w = weight * mask
                    if w.sum() == 0:
                        raise ValueError(f"No supported {key} distribution at {hand}/{angle}")
                    center = np.average(points, axis=0, weights=w)
                    zones[key] = {"center": center.round(4).tolist(), "cells": np.flatnonzero(mask).tolist(),
                                  "hb": [float(points[mask, 0].min()-.5), float(points[mask, 0].max()+.5)],
                                  "ivb": [float(points[mask, 1].min()-.5), float(points[mask, 1].max()+.5)],
                                  "whiff_pct": round(float(np.average(probability, weights=w) * 100), 2)}
                item["zones"] = zones
            slices.append(item)
        result[hand] = {"velocity_kmh": reference.velocity_kmh.iloc[0], "expectation_model": expectations[hand], "profiles": slices}
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
        print(f"movement zones {season}: {len(frame):,} shape pitches, {source['eligible_swings']:,} swings, {source['trackman_swings']:,} TrackMan swings", flush=True)
    frame = pd.concat(frames, ignore_index=True)
    if frame.pitch_id.duplicated().any():
        raise ValueError("Duplicate pitch IDs across seasons")
    pitches = {}
    for code, name in PITCH_NAMES.items():
        sample = frame[frame.code == code]
        outcomes = sample[sample.eligible_swing]
        if len(outcomes) < 1000 or outcomes.whiff.nunique() != 2:
            continue
        shape_train, shape_test = sample[sample.season < seasons[-1]], sample[sample.season == seasons[-1]]
        training_expectations = {hand: fit_expectation(shape_train[shape_train.hand == hand]) for hand in ("R", "L")}
        shape_validation = {hand: expectation_scores(shape_test[shape_test.hand == hand], training_expectations[hand])
                            if training_expectations[hand] and len(shape_test[shape_test.hand == hand]) >= 100 else None for hand in ("R", "L")}
        train = with_deltas(shape_train[shape_train.eligible_swing], training_expectations)
        test = with_deltas(shape_test[shape_test.eligible_swing], training_expectations)
        validation = None
        if len(train) >= 1000 and len(test) >= 100 and train.whiff.nunique() == test.whiff.nunique() == 2:
            full, baseline = fit_model(train), fit_model(train, False)
            validation = {"train_through": seasons[-2], "test_season": seasons[-1], "test_swings": len(test),
                          "movement": _scores(test.whiff, full.predict_proba(design(test))[:, 1]),
                          "controls_only": _scores(test.whiff, baseline.predict_proba(design(test, False))[:, 1])}
        expectations = {hand: fit_expectation(sample[sample.hand == hand]) for hand in ("R", "L")}
        fitted_outcomes = with_deltas(outcomes, expectations)
        model = fit_model(fitted_outcomes)
        pitches[code] = {"name": name, "swings": len(outcomes), "shape_pitches": len(sample), "validation": validation,
                         "shape_validation": shape_validation, "fastball_reference": code in {"FF", "SI", "FC"},
                         "model": {"intercept": model[-1].intercept_.tolist(), "coefficients": model[-1].coef_.tolist(),
                                   "mean": model[0].mean_.tolist(), "scale": model[0].scale_.tolist()},
                         "hands": profiles(sample, model, expectations)}
        print(f"movement zones {code}: fitted {len(sample):,} shape pitches and {len(fitted_outcomes):,} swings", flush=True)
    swings = int(frame.eligible_swing.sum())
    artifact = {"schema_version": 2, "angle_min": ANGLE_MIN, "angle_max": ANGLE_MAX, "step": 1,
                "shoulder_height_cm": SHOULDER_HEIGHT_CM, "window_deg": WINDOW_DEG,
                "min_swings": MIN_SWINGS, "min_pitchers": MIN_PITCHERS, "seasons": seasons,
                "swings": swings, "trackman_swings": int((frame.eligible_swing & frame.tm).sum()),
                "shape_pitches": len(frame), "trackman_shape_pitches": int(frame.tm.sum()), "sources": sources,
                "reference_time_s": REFERENCE_TIME_S, "expected_levels": [.5, .8],
                "grid": {"hb_min": -30, "ivb_min": -25, "hb_count": 61, "ivb_count": 56, "cell_size": 1},
                "references": REFERENCES,
                "angle_definition": "atan2(release_z_55_cm - 130, abs(release_x_55_cm)); fixed reference shoulder, no measured shoulder",
                "time_definition": "movement_0.4 = movement * (0.4 / flight_time)^2; flight computed from VB vy55/ay to plate front, from TrackMan release extension when matched, otherwise fixed 55 ft",
                "expectation_definition": "KBO-fitted conditional Gaussian for time-normalized HB/IVB given release-slot proxy, 55 ft HRA/VRA and flight time, separately by hand and pitch type; all eligible pitches, not only swings; no height-scaled extension or MLB fitted coefficients",
                "outcome": "whiff / swings; quadratic expected-movement deltas, release/context controls; plate center, 1-1 count, 50% opposite stance, hand-specific median velocity, latest season, VB source",
                "zone_definition": "expected 50%/80% Gaussian probability regions are shape expectations, not low-whiff grades; high/average/low whiff: upper 25%/middle 50%/lower 25% weighted model whiff probability, drawn as exact supported 1-inch cell boundaries",
                "pitches": pitches}
    destination = root / "web/data/movement_zones/profiles.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(artifact, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return swings


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    build_movement_zones(args.root.resolve())
