"""Research-only VB→TrackMan release bridge and seasonal eAA reference ranges.

No KBO measured arm-angle labels are available. The bridge is validated against
TrackMan coordinates; its downstream angle target is another model's prediction.
The exported reference envelope is NOT a validated KBO prediction interval.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler

from .arm_angle_calibration import features as angle_features, metrics, prepare_reference
from .curated import load_table
from .trackman_arm_angle import digest, load_height_table

BRIDGE_FEATURES = ["height_m", "arm_side_x55_m", "z55_m", "arm_side_dx_dy55", "dz_dy55"]
KEYS = ["season", "pitcher_id", "pitcher_name", "pitcher_hand"]
VB_COLUMNS = ["pitch_id", "game_id", "pitcher_id", "pitcher_name", "stadium", "pitch_type",
              "release_x_55", "release_z_55", "vx_55", "vy_55", "vz_55", "source_y0", "trajectory_valid"]
MIN_PITCHES = 100


def split_groups(groups, seed=42):
    """Predeclared 60/20/20 split of entire pitchers, independent of outcomes."""
    ids = np.array(sorted(set(map(str, groups))))
    if len(ids) < 15:
        raise ValueError("At least 15 pitchers required for train/calibration/test separation")
    np.random.default_rng(seed).shuffle(ids)
    a, b = int(.6*len(ids)), int(.8*len(ids))
    partitions = [set(ids[:a]), set(ids[a:b]), set(ids[b:])]
    return [np.asarray([str(g) in part for g in groups]) for part in partitions]


def conformal_radius(errors, groups, alpha=.10):
    """Finite-sample higher quantile of each calibration pitcher's max error.

    Seasons within a pitcher are not treated as independent calibration units.
    Coverage requires exchangeable future pitcher clusters in the same domain.
    """
    scores = pd.DataFrame({"group": groups, "error": np.abs(errors)}).groupby("group").error.max()
    if scores.empty or not np.isfinite(scores).all() or not 0 < alpha < 1:
        raise ValueError("Finite nonempty calibration errors and alpha in (0,1) required")
    rank = math.ceil((len(scores)+1)*(1-alpha))
    if rank > len(scores):
        raise ValueError("Too few calibration pitchers for requested finite radius")
    return float(np.sort(scores.to_numpy())[rank-1]), scores


def model_state(model):
    scaler, ridge = model.steps[-2][1], model.steps[-1][1]
    state = {"standardization_mean": scaler.mean_.tolist(), "standardization_scale": scaler.scale_.tolist(),
             "ridge_coefficients": ridge.coef_.tolist(), "intercept": np.asarray(ridge.intercept_).tolist()}
    if isinstance(model.steps[0][1], PolynomialFeatures):
        state["polynomial_powers"] = model.steps[0][1].powers_.tolist()
    return state


def bridge_features(frame):
    sign = frame.pitcher_hand.map({"Right": 1., "Left": -1.}).to_numpy(float)
    return np.column_stack([frame.height_cm.to_numpy(float)/100,
                            -sign*frame.release_x_55.to_numpy(float)/100,
                            frame.release_z_55.to_numpy(float)/100,
                            -sign*frame.vx_55.to_numpy(float)/frame.vy_55.to_numpy(float),
                            frame.vz_55.to_numpy(float)/frame.vy_55.to_numpy(float)])


def bridge_estimator():
    # Fixed before validation. No pitcher, stadium, or season categorical offsets.
    return make_pipeline(StandardScaler(), Ridge(alpha=10.))


def bridge_target(frame):
    sign = frame.pitcher_hand.map({"Right": 1., "Left": -1.}).to_numpy(float)
    return np.column_stack([sign*(frame.rel_side.to_numpy(float)+frame.release_x_55.to_numpy(float)/100),
                            frame.rel_height.to_numpy(float)-frame.release_z_55.to_numpy(float)/100])


def fit_bridge(frame):
    return bridge_estimator().fit(bridge_features(frame), bridge_target(frame))


def predict_bridge(model, frame):
    result = frame.copy()
    correction = model.predict(bridge_features(frame))
    sign = frame.pitcher_hand.map({"Right": 1., "Left": -1.}).to_numpy(float)
    result["pred_rel_side"] = -frame.release_x_55.to_numpy(float)/100 + sign*correction[:, 0]
    result["pred_rel_height"] = frame.release_z_55.to_numpy(float)/100 + correction[:, 1]
    return result


def aggregate(frame, extra_keys=(), targets=False):
    keys = KEYS + list(extra_keys)
    numeric = ["release_x_55", "release_z_55", "vx_55", "vy_55", "vz_55", "height_cm"]
    if targets:
        numeric += ["rel_side", "rel_height"]
    data = frame.copy()
    # Mean velocity ratios, not ratio of mean velocities: preserves linear bridge.
    data["dx_dy55"] = data.vx_55/data.vy_55
    data["dz_dy55"] = data.vz_55/data.vy_55
    numerical = numeric+["dx_dy55", "dz_dy55"]
    if "n_pitches" not in data:
        data["n_pitches"] = 1
    if "pred_rel_side" in data:
        numerical += ["pred_rel_side", "pred_rel_height"]
    if "source_y0" in data:
        data["source_55_share"] = data.source_y0.eq(55).astype(float)
    if "source_55_share" in data:
        numerical += ["source_55_share"]
    if "outside_bridge" in data:
        numerical += ["outside_bridge"]
    weighted = data[keys+numerical].copy()
    for column in numerical:
        weighted[column] = data[column]*data.n_pitches
    result = weighted.groupby(keys, dropna=False)[numerical].sum().join(
        data.groupby(keys, dropna=False).n_pitches.sum()).reset_index()
    for column in numerical:
        result[column] /= result.n_pitches
    # bridge_features uses ratio of velocities; override these with exact means.
    result["vy_55"] = -1.
    result["vx_55"] = -result.dx_dy55
    result["vz_55"] = -result.dz_dy55
    return result


def valid_vb(frame):
    return (frame.trajectory_valid.fillna(False) & frame.release_x_55.between(-200, 200)
            & frame.release_z_55.between(5, 270) & frame.vy_55.lt(0)
            & np.isfinite(frame[["vx_55", "vy_55", "vz_55"]]).all(axis=1)
            & frame.height_cm.between(140, 220) & frame.pitcher_hand.isin(["Right", "Left"]))


def reference_model(reference):
    train, calibration, test = split_groups(reference.pitcher)
    model = make_pipeline(PolynomialFeatures(degree=2, include_bias=False), StandardScaler(), Ridge(alpha=10.))
    model.fit(angle_features(reference.loc[train]), reference.loc[train, "arm_angle"])
    output = reference.copy()
    output["split"] = np.select([train, calibration], ["train", "calibration"], default="test")
    output["prediction_deg"] = model.predict(angle_features(reference))
    output["error_deg"] = output.prediction_deg-output.arm_angle
    radius, scores = conformal_radius(output.loc[calibration, "error_deg"], output.loc[calibration, "pitcher"])
    test_rows = output.loc[test]
    report = {"split_seed": 42, "split_unit": "entire MLB pitcher, all seasons together",
              "splits": {s: {"rows": len(g), "pitchers": int(g.pitcher.nunique())} for s, g in output.groupby("split")},
              "radius_90_deg": radius, "calibration_pitchers": len(scores),
              "test_metrics": metrics(test_rows.arm_angle, test_rows.prediction_deg),
              "test_season_coverage": float(test_rows.error_deg.abs().le(radius).mean()),
              "test_pitcher_all_seasons_coverage": float(test_rows.groupby("pitcher").error_deg.apply(lambda x: x.abs().max() <= radius).mean()),
              "status": "90pct cluster split-conformal reference on MLB qualified seasons, NOT verified in KBO",
              "training_feature_min": angle_features(reference.loc[train]).min(axis=0).tolist(),
              "training_feature_max": angle_features(reference.loc[train]).max(axis=0).tolist(),
              "fitted_model": model_state(model)}
    return model, reference.loc[train].copy(), report, output


def seasonal_comparison(predicted_games, angle_model):
    seasons = aggregate(predicted_games, targets=True)
    estimated = seasons.rename(columns={"rel_side": "truth_rel_side", "rel_height": "truth_rel_height",
                                         "pred_rel_side": "rel_side", "pred_rel_height": "rel_height"})
    seasons["vb_eaa_deg"] = angle_model.predict(angle_features(estimated))
    truth = seasons.copy()
    seasons["tm_model_eaa_deg"] = angle_model.predict(angle_features(truth))
    seasons["error_deg"] = seasons.vb_eaa_deg-seasons.tm_model_eaa_deg
    seasons["side_error_cm"] = 100*(seasons.pred_rel_side-seasons.rel_side)
    seasons["height_error_cm"] = 100*(seasons.pred_rel_height-seasons.rel_height)
    return seasons


def comparison_report(games, angle_model, radius=None):
    seasons = seasonal_comparison(games, angle_model)
    eligible = seasons.n_pitches.ge(MIN_PITCHES)
    selected = seasons.loc[eligible]
    result = {"game_rows": len(games), "season_rows": len(seasons), "eligible_season_rows": len(selected),
              "pitchers": int(selected.pitcher_id.nunique()),
              "game_side_error_cm": coordinate_metrics(100*games.rel_side, 100*games.pred_rel_side),
              "game_height_error_cm": coordinate_metrics(100*games.rel_height, 100*games.pred_rel_height)}
    if len(selected):
        result["season_eaa_vs_TM_model"] = metrics(selected.tm_model_eaa_deg, selected.vb_eaa_deg)
        result["season_side_error_cm"] = coordinate_metrics(100*selected.rel_side, 100*selected.pred_rel_side)
        result["season_height_error_cm"] = coordinate_metrics(100*selected.rel_height, 100*selected.pred_rel_height)
        if radius is not None:
            result["bridge_reference_coverage_seasons"] = float(selected.error_deg.abs().le(radius).mean())
            result["bridge_reference_coverage_pitchers_all_seasons"] = float(selected.groupby("pitcher_id").error_deg.apply(lambda x: x.abs().max() <= radius).mean())
    return result, seasons


def coordinate_metrics(truth, prediction):
    return {key.replace("_deg", "_cm"): value for key, value in metrics(truth, prediction).items()}


def validate_bridge(games, angle_model):
    historical = games[games.season < 2024].reset_index(drop=True)
    future = games[games.season == 2024].reset_index(drop=True)
    train, calibration, test = split_groups(historical.pitcher_id)
    model = fit_bridge(historical.loc[train])
    calibration_games = predict_bridge(model, historical.loc[calibration])
    calibration_seasons = seasonal_comparison(calibration_games, angle_model)
    eligible = calibration_seasons.n_pitches.ge(MIN_PITCHES)
    radius, scores = conformal_radius(calibration_seasons.loc[eligible, "error_deg"],
                                      calibration_seasons.loc[eligible, "pitcher_id"])
    report = {"estimator": "linear standardized Ridge alpha=10 on TM-minus-VB coordinate residuals, equal weight per pitcher-game",
              "features": BRIDGE_FEATURES, "training_seasons": sorted(historical.season.unique().tolist()),
              "minimum_matched_pitches_per_season": MIN_PITCHES, "split_unit": "entire KBO pitcher across 2019–2023",
              "radius_90_deg_vs_TM_model": radius, "calibration_pitchers": len(scores),
              "splits": {s: {"game_rows": int(mask.sum()), "pitchers": int(historical.loc[mask, "pitcher_id"].nunique())}
                         for s, mask in zip(["train", "calibration", "test"], [train, calibration, test])},
              "fitted_model": model_state(model), "validation": {},
              "training_feature_min": bridge_features(historical.loc[train]).min(axis=0).tolist(),
              "training_feature_max": bridge_features(historical.loc[train]).max(axis=0).tolist(),
              "target_note": "TM-model eAA is a proxy, NOT measured KBO arm angle; coordinate metrics are at pitcher-game/season means"}
    outputs = []
    for label, part in [("pitcher_split_test", historical.loc[test]), ("forward_2024", future)]:
        result, scored = comparison_report(predict_bridge(model, part), angle_model, radius)
        report["validation"][label] = result
        scored["evaluation"] = label
        outputs.append(scored)
    cv_results = []
    for fold, (fit, held) in enumerate(GroupKFold(5, shuffle=True, random_state=42).split(historical, groups=historical.pitcher_id), 1):
        assert not set(historical.pitcher_id.iloc[fit]) & set(historical.pitcher_id.iloc[held])
        cv_model = fit_bridge(historical.iloc[fit])
        _, scored = comparison_report(predict_bridge(cv_model, historical.iloc[held]), angle_model)
        scored["evaluation"] = "pitcher_group_cv"
        scored["fold"] = fold
        cv_results.append(scored)
    cv = pd.concat(cv_results, ignore_index=True)
    selected = cv[cv.n_pitches.ge(MIN_PITCHES)]
    report["validation"]["pitcher_group_cv"] = {"season_eaa_vs_TM_model": metrics(selected.tm_model_eaa_deg, selected.vb_eaa_deg),
                                                  "pitchers": int(selected.pitcher_id.nunique()), "season_rows": len(selected)}
    outputs.append(cv)
    report["validation"]["leave_stadium_out"] = {}
    for stadium in sorted(historical.stadium.unique()):
        fit, held = historical.stadium.ne(stadium), historical.stadium.eq(stadium)
        park_model = fit_bridge(historical.loc[fit])
        result, scored = comparison_report(predict_bridge(park_model, historical.loc[held]), angle_model, radius)
        report["validation"]["leave_stadium_out"][stadium] = result
        scored["evaluation"] = "leave_stadium_out"
        scored["held_out_stadium"] = stadium
        outputs.append(scored)
    # Fixed 55ft substitution baseline on the same forward holdout.
    baseline = future.copy()
    baseline["pred_rel_side"] = -baseline.release_x_55/100
    baseline["pred_rel_height"] = baseline.release_z_55/100
    report["validation"]["forward_2024_unbridged_baseline"], _ = comparison_report(baseline, angle_model)
    calibration_seasons["evaluation"] = "bridge_calibration"
    outputs.append(calibration_seasons)
    return model, historical.loc[train].copy(), report, pd.concat(outputs, ignore_index=True)


def attach_interval(frame, angle_model, angle_training, bridge_training, mlb_radius, bridge_radius):
    seasons = frame.copy()
    estimated = seasons.rename(columns={"pred_rel_side": "rel_side", "pred_rel_height": "rel_height"})
    x = angle_features(estimated)
    raw = angle_model.predict(x)
    domain = angle_features(angle_training)
    outside_mlb = ((x < domain.min(axis=0)) | (x > domain.max(axis=0))).any(axis=1)
    bridge_x, bridge_domain = bridge_features(seasons), bridge_features(bridge_training)
    outside_bridge = ((bridge_x < bridge_domain.min(axis=0)) | (bridge_x > bridge_domain.max(axis=0))).any(axis=1)
    eligible = seasons.n_pitches.ge(MIN_PITCHES) & ~outside_mlb & ~outside_bridge & np.isfinite(raw) & (np.abs(raw) <= 90)
    seasons["model_raw_eaa_deg"] = raw
    seasons["eaa_deg"] = np.where(eligible, raw, np.nan)
    seasons["outside_MLB_training_range"] = outside_mlb
    seasons["outside_bridge_training_range"] = outside_bridge
    seasons["bridge_reference_radius_deg"] = np.where(eligible, bridge_radius, np.nan)
    seasons["mlb_reference_radius_deg"] = np.where(eligible, mlb_radius, np.nan)
    radius = mlb_radius+bridge_radius  # Envelope sum; no independence assumption, no KBO coverage claim.
    seasons["reference_low_deg"] = np.where(eligible, np.maximum(-90, raw-radius), np.nan)
    seasons["reference_high_deg"] = np.where(eligible, np.minimum(90, raw+radius), np.nan)
    seasons["range_kind"] = "sum_of_two_90pct_reference_radii_KBO_coverage_unknown"
    seasons["estimate_status"] = np.select([outside_mlb, outside_bridge, seasons.n_pitches.lt(MIN_PITCHES), ~eligible],
                                            ["withheld_MLB_extrapolation", "withheld_bridge_extrapolation", "withheld_small_sample", "withheld_invalid_prediction"],
                                            default="estimated_KBO_angle_unvalidated")
    seasons["unseen_stadium"] = seasons.get("unseen_stadium", pd.Series(False, index=seasons.index)).astype(bool)
    seasons["future_season"] = seasons.season.gt(2024)
    seasons["source_plane_55_present"] = seasons.source_55_share.gt(0)
    # Park holdouts show that the known-park bridge radius fails to cover several
    # unseen parks. Do not export a finite full reference envelope for those rows.
    seasons["range_status"] = np.select(
        [~eligible, seasons.unseen_stadium, seasons.future_season],
        ["withheld_estimate", "unavailable_unseen_stadium_bias", "reference_only_future_season_unvalidated"],
        default="reference_only_KBO_angle_unvalidated")
    seasons.loc[seasons.unseen_stadium, ["reference_low_deg", "reference_high_deg"]] = np.nan
    return seasons


def y2y_comparisons(seasons, park_means, angle_model, angle_training=None):
    outputs = []
    for (player, hand), group in seasons.groupby(["pitcher_id", "pitcher_hand"]):
        group = group.sort_values("season")
        for i in range(1, len(group)):
            previous, current = group.iloc[i-1], group.iloc[i]
            if current.season != previous.season+1:
                continue
            row = {"pitcher_id": player, "pitcher_name": current.pitcher_name, "pitcher_hand": hand,
                   "previous_season": int(previous.season), "season": int(current.season),
                   "previous_eaa_deg": previous.eaa_deg, "eaa_deg": current.eaa_deg,
                   "raw_change_deg": current.eaa_deg-previous.eaa_deg,
                   "common_park_change_deg": np.nan, "common_parks": 0,
                   "common_park_status": "unavailable",
                   "range_kind": "reference_envelope_for_difference_KBO_coverage_unknown"}
            parks = park_means[(park_means.pitcher_id == player) & (park_means.pitcher_hand == hand)]
            a = parks[(parks.season == previous.season) & (parks.n_pitches >= 30)].set_index("stadium")
            b = parks[(parks.season == current.season) & (parks.n_pitches >= 30)].set_index("stadium")
            common = sorted(set(a.index) & set(b.index))
            row["common_parks"] = len(common)
            row["previous_common_park_share"] = float(a.loc[common].n_pitches.sum()/previous.n_pitches)
            row["current_common_park_share"] = float(b.loc[common].n_pitches.sum()/current.n_pitches)
            if common and pd.notna(row["raw_change_deg"]):
                a, b = a.loc[common], b.loc[common]
                weights = .5*(a.n_pitches/a.n_pitches.sum()+b.n_pitches/b.n_pitches.sum())
                inputs = []
                for item in (a, b):
                    inputs.append({"height_cm": float((item.height_cm*weights).sum()), "pitcher_hand": hand,
                                   "rel_side": float((item.pred_rel_side*weights).sum()),
                                   "rel_height": float((item.pred_rel_height*weights).sum())})
                x = angle_features(pd.DataFrame(inputs))
                outside = False
                if angle_training is not None:
                    domain = angle_features(angle_training)
                    outside = ((x < domain.min(axis=0)) | (x > domain.max(axis=0))).any()
                if not outside:
                    angles = angle_model.predict(x)
                    row["common_park_change_deg"] = float(angles[1]-angles[0])
                    row["common_park_status"] = "composition_standardized_KBO_unvalidated"
                else:
                    row["common_park_status"] = "withheld_MLB_extrapolation"
            row["change_reference_low_deg"] = current.reference_low_deg-previous.reference_high_deg
            row["change_reference_high_deg"] = current.reference_high_deg-previous.reference_low_deg
            row["status"] = "direction_unresolved_by_reference_envelope"
            if pd.isna(row["raw_change_deg"]):
                row["status"] = "withheld_missing_season_estimate"
            elif pd.isna(row["change_reference_low_deg"]):
                row["status"] = "direction_unresolved_unseen_stadium_range_unavailable"
            elif row["change_reference_low_deg"] > 0 or row["change_reference_high_deg"] < 0:
                row["status"] = "direction_outside_reference_envelope_still_KBO_unvalidated"
            row["future_season"] = bool(current.future_season)
            row["source_plane_55_present"] = bool(current.source_plane_55_present)
            outputs.append(row)
    return pd.DataFrame(outputs)


def run(root: Path, matched_dir: Path, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    cache = root / ".cache/arm_angle/vb_bridge"
    cache.mkdir(parents=True, exist_ok=True)
    bio_path = root / "data/curated/players/player_bio.parquet"
    height_path = root / "data/tracking/player_heights.csv"
    bio = pd.read_parquet(bio_path)
    heights = load_height_table(height_path, bio)
    lookups = bio[["player_id", "player_name", "throws"]].merge(heights[["player_id", "height_cm"]], on="player_id", how="left", validate="one_to_one")
    lookup = lookups.rename(columns={"player_id": "pitcher_id", "player_name": "bio_name"})
    lookup["pitcher_hand"] = lookup.throws.map({"R": "Right", "L": "Left"})
    matched_games, all_games, source_audits, source_changes, eligibility_tables, hashes = [], [], [], [], [], {}
    years = list(range(2019, 2027))
    for year in years:
        canonical = load_table(root, "pitches", year, columns=VB_COLUMNS).to_pandas()
        if canonical.pitch_id.duplicated().any():
            raise ValueError(f"Duplicate canonical pitch ID in season {year}")
        # Hash the exact selected canonical input content, not mutable caches.
        hashes[f"canonical_selected_columns_{year}"] = hashlib.sha256(
            pd.util.hash_pandas_object(canonical, index=False).to_numpy().tobytes()).hexdigest()
        canonical["season"] = year
        canonical = canonical.merge(lookup, on="pitcher_id", how="left", validate="many_to_one")
        name_mismatch = canonical.pitcher_name.ne(canonical.bio_name)
        canonical.loc[name_mismatch, "height_cm"] = np.nan
        valid = valid_vb(canonical)
        eligibility = canonical[["season", "pitcher_id", "pitcher_name", "pitcher_hand"]].copy()
        eligibility["input_status"] = np.select(
            [name_mismatch, canonical.height_cm.isna(), canonical.pitcher_hand.isna(), ~valid],
            ["bio_name_mismatch", "missing_verified_height", "missing_hand", "invalid_trajectory_or_release"],
            default="valid")
        eligibility_tables.append(eligibility.groupby(KEYS+["input_status"], dropna=False).size().rename("n_pitches").reset_index())
        audit = {"season": year, "rows": len(canonical), "valid_for_estimation": int(valid.sum()),
                 "missing_height_pitches": int(canonical.height_cm.isna().sum()),
                 "missing_height_pitchers": int(canonical.loc[canonical.height_cm.isna(), "pitcher_id"].nunique()),
                 "missing_hand_pitches": int(canonical.pitcher_hand.isna().sum()),
                 "bio_name_mismatch_pitches": int(name_mismatch.sum()),
                 "source_planes": {str(k): int(v) for k, v in canonical.source_y0.value_counts(dropna=False).items()},
                 "stadiums": sorted(canonical.stadium.dropna().unique().tolist())}
        source_audits.append(audit)
        selected = canonical.loc[valid].copy()
        all_games.append(aggregate(selected, ["game_id", "stadium"]))
        # Keep pitch-type-conditioned source-plane transition diagnostics separately.
        if year == 2026:
            source_changes.append(selected.groupby(["pitcher_id", "stadium", "pitch_type", "source_y0"], dropna=False).agg(
                n_pitches=("pitch_id", "size"), x55_cm=("release_x_55", "mean"), z55_cm=("release_z_55", "mean")).reset_index())
        if year <= 2024:
            path = matched_dir / f"matched_{year}.parquet"
            hashes[f"matched_{year}"] = digest(path)
            matched = pd.read_parquet(path)
            if matched.pitch_id.duplicated().any():
                raise ValueError(f"Duplicate matched pitch ID in season {year}")
            matched = matched.drop(columns=[c for c in ("vx_55", "vy_55", "vz_55", "source_y0") if c in matched])
            matched = matched.merge(canonical[["pitch_id", "vx_55", "vy_55", "vz_55", "source_y0", "height_cm", "pitcher_hand"]].rename(columns={"pitcher_hand": "bio_hand"}), on="pitch_id", how="left", validate="one_to_one")
            matched["season"] = year
            hand_disagreement = matched.bio_hand.notna() & matched.pitcher_hand.ne(matched.bio_hand)
            keep = valid_vb(matched) & matched.rel_side.between(-2, 2) & matched.rel_height.between(.05, 2.7) & ~hand_disagreement
            audit["matched_rows"] = len(matched)
            audit["matched_valid"] = int(keep.sum())
            audit["matched_hand_disagreement"] = int(hand_disagreement.sum())
            matched_games.append(aggregate(matched.loc[keep], ["game_id", "stadium"], targets=True))
        print(json.dumps(audit, ensure_ascii=False), flush=True)
    paired = pd.concat(matched_games, ignore_index=True)
    games = pd.concat(all_games, ignore_index=True)
    pd.concat(eligibility_tables, ignore_index=True).to_csv(output / "eaa_input_eligibility.csv", index=False)
    paired.to_parquet(cache / "matched_pitcher_games.parquet", index=False)
    reference_path = root / "analysis/arm_angle/results/mlb_reference.csv"
    reference, excluded = prepare_reference(pd.read_csv(reference_path, dtype={"pitcher": str}))
    angle_model, angle_training, angle_report, reference_predictions = reference_model(reference)
    reference_predictions.to_csv(output / "eaa_mlb_split_validation.csv", index=False)
    bridge, bridge_training, bridge_report, validation = validate_bridge(paired, angle_model)
    validation.to_csv(output / "eaa_bridge_validation.csv", index=False)
    prediction = predict_bridge(bridge, games)
    training_x = bridge_features(bridge_training)
    prediction["outside_bridge"] = ((bridge_features(games) < training_x.min(axis=0)) | (bridge_features(games) > training_x.max(axis=0))).any(axis=1)
    radius_mlb, radius_bridge = angle_report["radius_90_deg"], bridge_report["radius_90_deg_vs_TM_model"]
    seasons = aggregate(prediction)
    known_parks = set(bridge_training.stadium)
    unseen = prediction.assign(unseen=lambda d: ~d.stadium.isin(known_parks)).groupby(KEYS, dropna=False).unseen.any()
    seasons = seasons.merge(unseen.rename("unseen_stadium").reset_index(), on=KEYS, validate="one_to_one")
    seasons = attach_interval(seasons, angle_model, angle_training, bridge_training, radius_mlb, radius_bridge)
    seasons.to_csv(output / "eaa_vb_pitcher_seasons_2019_2026.csv", index=False)
    seasons[seasons.season.ge(2022)].to_csv(output / "eaa_vb_pitcher_seasons_2022_2026.csv", index=False)
    parks = aggregate(prediction, ["stadium"])
    parks["unseen_stadium"] = ~parks.stadium.isin(known_parks)
    parks = attach_interval(parks, angle_model, angle_training, bridge_training, radius_mlb, radius_bridge)
    parks.to_csv(output / "eaa_vb_pitcher_stadium_seasons.csv", index=False)
    y2y = y2y_comparisons(seasons, parks, angle_model, angle_training)
    y2y.to_csv(output / "eaa_vb_y2y.csv", index=False)
    y2y[y2y.previous_season.ge(2022)].to_csv(output / "eaa_vb_y2y_2022_2026.csv", index=False)
    changes = pd.concat(source_changes, ignore_index=True)
    a, b = [changes[changes.source_y0.eq(plane)].drop(columns="source_y0") for plane in (50, 55)]
    change = a.merge(b, on=["pitcher_id", "stadium", "pitch_type"], suffixes=("_50", "_55"), validate="one_to_one")
    change = change[change.n_pitches_50.ge(30) & change.n_pitches_55.ge(30)].copy()
    change["x55_shift_cm"] = change.x55_cm_55-change.x55_cm_50
    change["z55_shift_cm"] = change.z55_cm_55-change.z55_cm_50
    change.to_csv(output / "eaa_2026_source_plane_transition.csv", index=False)
    hashes.update({"bio": digest(bio_path), "heights": digest(height_path), "reference": digest(reference_path),
                   "implementation": digest(Path(__file__)), "angle_features_implementation": digest(root / "src/visualbaseball/arm_angle_calibration.py"),
                   "matching_implementation": digest(root / "analysis/movement_calibration/match_trackman.py"),
                   "canonical_implementation": digest(root / "src/visualbaseball/curated.py")})
    report = {"target": "eAA: estimated Savant frontal arm angle, pitcher-season mean", "schema_version": 1,
              "runtime": {"python": sys.version.split()[0], **{package: version(package) for package in ("numpy", "pandas", "pyarrow", "scikit-learn", "scipy")}},
              "source_audits": source_audits, "MLB_reference_model": angle_report, "VB_TM_bridge": bridge_report,
              "input_hashes": hashes, "excluded_reference_rows": excluded,
              "range_definition": {"kind": "reference_envelope_NOT_KBO_prediction_interval", "mlb_radius_deg": radius_mlb,
                                   "bridge_radius_deg": radius_bridge, "total_radius_deg": radius_mlb+radius_bridge,
                                   "nominal_component_coverage": .90,
                                   "joint_coverage": "unknown in KBO; if both components have 90pct coverage in the same target population, union bound gives a lower bound of 80pct, not 90pct; those conditions are not established in KBO",
                                   "small_sample": "withhold seasonal eAA below 100 valid pitches", "domain": "withhold seasonal mean outside either model's marginal feature bounds; bounds do not certify joint support",
                                   "unseen_stadium": "point estimate flagged, finite reference envelope suppressed: park holdouts failed known-park radius; no Gwangju reference labels", "future_season": "flag for 2025–2026; no contemporaneous TM truth"},
              "outputs_by_year": {}, "y2y_statuses": {str(k): int(v) for k, v in y2y.status.value_counts().items()},
              "source_plane_transition": {"matched_pitcher_park_pitchtype_strata": len(change),
                                           "median_x55_shift_cm": float(change.x55_shift_cm.median()),
                                           "median_z55_shift_cm": float(change.z55_shift_cm.median()),
                                           "interpretation": "within pitcher/park/pitch-type BEFORE vs AFTER descriptive changes; period is confounded with source plane, cannot identify equipment bias or mechanics causally"},
              "limitations": ["No measured KBO shoulder-ball arm-angle labels: actual eAA accuracy and interval coverage remain unknown.",
                              "Forward/park tests compare to TM-model eAA, not measured arm angle; 2024 holdout cannot verify 2025–2026 or Gwangju bias.",
                              "Present-day verified heights are reused across historical seasons, not historical measurements.",
                              "All years use the same frozen models; no forced annual league mean or pitcher continuity.",
                              "Training on matched pitches may select on pitch speed and matching quality.",
                              "Global year drift and pitcher mechanics are not identifiable without external anchors.",
                              "Reference range sum is not a KBO confidence interval; two component90% ranges do not create joint90% coverage.",
                              "Common-park Y2Y controls stadium mixture only; pitch-type, velocity, injury, sample and measurement changes remain."]}
    for year, group in seasons.groupby("season"):
        report["outputs_by_year"][str(year)] = {"pitcher_seasons": len(group), "estimated": int(group.eaa_deg.notna().sum()),
                                                "statuses": {str(k): int(v) for k, v in group.estimate_status.value_counts().items()},
                                                "range_statuses": {str(k): int(v) for k, v in group.range_status.value_counts().items()},
                                                "unseen_stadium_pitcher_seasons": int(group.unseen_stadium.sum())}
    (output / "eaa_bridge_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n")
    print(json.dumps({"MLB_test": angle_report["test_metrics"], "reference_radius": report["range_definition"],
                      "forward_2024": bridge_report["validation"]["forward_2024"], "outputs_by_year": report["outputs_by_year"]}, ensure_ascii=False, indent=2), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--matched-dir", type=Path, default=Path(".cache/arm_angle/vb_bridge/matched"))
    parser.add_argument("--out", type=Path, default=Path("analysis/arm_angle/results"))
    args = parser.parse_args()
    run(args.root.resolve(), args.matched_dir.resolve(), args.out.resolve())


if __name__ == "__main__":
    main()
