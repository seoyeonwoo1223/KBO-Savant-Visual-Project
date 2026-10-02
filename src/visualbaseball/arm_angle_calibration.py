"""Validate MLB pitcher-season arm-angle prediction and transfer it to KBO.

Only seasonal means are predicted: seasonal reference labels cannot validate
pitch-by-pitch angles. Entire pitchers are held out during cross-validation.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler

from .trackman_arm_angle import Assumptions, digest, score

FEATURE_NAMES = ["height_m", "release_height_over_height", "arm_side_release_over_height", "left_hand"]


def features(frame):
    h = pd.to_numeric(frame.height_cm).to_numpy(float)/100
    hand = frame.pitcher_hand.map({"Right": 1., "Left": -1.}).to_numpy(float)
    return np.column_stack([h, frame.rel_height.to_numpy(float)/h,
                            hand*frame.rel_side.to_numpy(float)/h, (hand < 0).astype(float)])


def metrics(truth, prediction):
    error = np.asarray(prediction)-np.asarray(truth)
    return {"n": len(error), "mae_deg": float(np.mean(np.abs(error))),
            "rmse_deg": float(np.sqrt(np.mean(error**2))), "bias_deg": float(np.mean(error)),
            "abs_error_p90_deg": float(np.quantile(np.abs(error), .90))}


def prepare_reference(data):
    needed = {"pitcher", "season", "arm_angle", "height_cm", "pitch_hand", "rel_height_m", "rel_side_m",
              "reference_source_url", "reference_source_sha256", "height_source_url", "height_source_sha256"}
    if not needed.issubset(data.columns):
        raise ValueError(f"Missing reference fields: {sorted(needed-set(data.columns))}")
    if data.duplicated(["pitcher", "season"]).any():
        raise ValueError("Reference rows must be unique pitcher-seasons")
    data = data.rename(columns={"rel_height_m": "rel_height", "rel_side_m": "rel_side"}).copy()
    data["pitcher_hand"] = data.pitch_hand.map({"R": "Right", "L": "Left"})
    data["extension"] = np.nan  # No matched MLB extension in these reference pages.
    for column in ("arm_angle", "height_cm", "rel_height", "rel_side"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    valid = (data.arm_angle.between(-90, 90) & data.height_cm.between(140, 220)
             & data.rel_height.between(.05, 2.7) & data.rel_side.between(-2, 2)
             & data.pitcher_hand.notna())
    for field in ("reference_source_url", "height_source_url"):
        valid &= data[field].fillna("").str.startswith("https://")
    for field in ("reference_source_sha256", "height_source_sha256"):
        valid &= data[field].fillna("").str.fullmatch(r"[0-9a-f]{64}")
    return data.loc[valid].reset_index(drop=True), int((~valid).sum())


def fit_reference(reference, folds=5):
    if reference.pitcher.nunique() < folds or len(reference) < 30:
        raise ValueError("Calibration requires at least 30 reference observations and one distinct pitcher per fold")
    x, truth = features(reference), reference.arm_angle.to_numpy(float)
    # Predeclared model/regularization; holdout errors are not used for tuning.
    def estimator():
        return make_pipeline(PolynomialFeatures(degree=2, include_bias=False), StandardScaler(), Ridge(alpha=10.))
    splitter = GroupKFold(n_splits=folds, shuffle=True, random_state=42)
    predictions = np.full(len(reference), np.nan)
    predictions_without_height = np.full(len(reference), np.nan)
    sign = reference.pitcher_hand.map({"Right": 1., "Left": -1.}).to_numpy(float)
    x_without_height = np.column_stack([reference.rel_height, sign*reference.rel_side, (sign < 0).astype(float)])
    held_out_fold = np.zeros(len(reference), dtype=int)
    splits = []
    for fold, (train, test) in enumerate(splitter.split(x, truth, groups=reference.pitcher), 1):
        train_ids, test_ids = set(reference.pitcher.iloc[train]), set(reference.pitcher.iloc[test])
        if train_ids & test_ids:
            raise AssertionError("Pitcher leakage across reference folds")
        model = estimator().fit(x[train], truth[train])
        predictions[test] = model.predict(x[test])
        ablation = estimator().fit(x_without_height[train], truth[train])
        predictions_without_height[test] = ablation.predict(x_without_height[test])
        held_out_fold[test] = fold
        splits.append({"fold": fold, "train_rows": len(train), "test_rows": len(test),
                       "train_pitchers": len(train_ids), "test_pitchers": len(test_ids), "pitcher_overlap": 0})
    scored = score(reference)
    reference = reference.copy()
    reference["oof_prediction_deg"] = predictions
    reference["oof_without_height_deg"] = predictions_without_height
    reference["held_out_fold"] = held_out_fold
    reference["error_deg"] = predictions-truth
    reference["fixed_130cm_proxy_deg"] = scored.fixed_130cm_proxy_deg
    reference["height_scenario_deg"] = scored.estimated_frontal_deg
    # Paired cluster bootstrap preserves all seasons of a sampled pitcher.
    paired = pd.DataFrame({"pitcher": reference.pitcher,
                           "improvement": np.abs(predictions_without_height-truth)-np.abs(predictions-truth)})
    clusters = paired.groupby("pitcher").improvement.agg(["sum", "count"])
    rng = np.random.default_rng(42)
    samples = rng.integers(0, len(clusters), size=(2000, len(clusters)))
    bootstrap = clusters["sum"].to_numpy()[samples].sum(axis=1)/clusters["count"].to_numpy()[samples].sum(axis=1)
    report = {"estimator": "degree-2 polynomial, standardized features, Ridge alpha=10, fixed before evaluation",
              "features": FEATURE_NAMES, "extension_status": "not included: matching MLB reference extension unavailable; retained as KBO diagnostic",
              "validation": "5-fold GroupKFold by entire MLB pitcher, shuffled random_state=42",
              "reference_rows": len(reference), "reference_pitchers": int(reference.pitcher.nunique()),
              "folds": splits, "model_oof": metrics(truth, predictions),
              "without_height_oof": metrics(truth, predictions_without_height),
              "height_ablation_mae_improvement_deg": {"observed": float(paired.improvement.mean()),
                                                       "MLB_pitcher_cluster_bootstrap_95pct": np.quantile(bootstrap, [.025, .975]).tolist(),
                                                       "bootstrap_samples": 2000},
              "fixed_130cm_baseline": metrics(truth, scored.fixed_130cm_proxy_deg),
              "height_scenario_baseline": metrics(truth, scored.estimated_frontal_deg),
              "by_hand": {}, "by_reference_slot": {},
              "kbo_validation_status": "unvalidated_no_KBO_measured_arm_angle_labels",
              "population_note": "MLB qualified pitcher-season aggregates, not all pitches or all pitchers",
              "interval_note": "OOF absolute-error quantiles describe MLB holdouts only; they are not KBO confidence intervals"}
    for value, group in reference.groupby("pitcher_hand"):
        report["by_hand"][value] = metrics(group.arm_angle, group.oof_prediction_deg)
    reference["reference_slot"] = pd.cut(reference.arm_angle, [-91, 0, 20, 60, 91], right=False,
                                         labels=["underhand", "low_slot", "three_quarter", "high_slot"])
    for value, group in reference.groupby("reference_slot", observed=True):
        report["by_reference_slot"][str(value)] = metrics(group.arm_angle, group.oof_prediction_deg)
    model = estimator().fit(x, truth)
    polynomial, scaler, ridge = model.steps[0][1], model.steps[1][1], model.steps[2][1]
    report["fitted_model"] = {"polynomial_feature_names": polynomial.get_feature_names_out(FEATURE_NAMES).tolist(),
                               "standardization_mean": scaler.mean_.tolist(), "standardization_scale": scaler.scale_.tolist(),
                               "ridge_coefficients": ridge.coef_.tolist(), "intercept": float(ridge.intercept_),
                               "training_feature_min": x.min(axis=0).tolist(), "training_feature_max": x.max(axis=0).tolist()}
    return model, report, reference


def transfer(model, reference, pitches):
    # Use means, since the official labels are seasonal mean angles/positions.
    valid = pitches.release_valid & pitches.height_cm.notna() & pitches.pitcher_hand.isin(["Right", "Left"])
    keys = ["season", "pitcher_trackman_id", "player_id", "player_name", "pitcher_hand"]
    grouped = pitches.loc[valid].groupby(keys, dropna=False).agg(
        n_release_pitches=("trackman_id", "size"), rel_height=("rel_height", "mean"),
        rel_side=("rel_side", "mean"), height_cm=("height_cm", "first"),
        extension_mean_m=("extension", lambda x: x.where(x.between(.5, 3)).mean())).reset_index()
    if grouped.empty:
        grouped["mlb_calibrated_season_angle_deg"] = pd.Series(dtype=float)
        grouped["transfer_status"] = pd.Series(dtype=str)
        return grouped
    x = features(grouped)
    training = features(reference)
    outside = ((x < training.min(axis=0)) | (x > training.max(axis=0))).any(axis=1)
    prediction = model.predict(x)
    grouped["model_raw_prediction_deg"] = prediction
    angle_ok = (prediction >= -90) & (prediction <= 90)
    # Preserve unconstrained extrapolation in an audit column; do not clip it
    # into plausible values and pass it off as a successful estimate.
    grouped["mlb_calibrated_season_angle_deg"] = np.where(angle_ok & ~outside, prediction, np.nan)
    grouped["outside_training_feature_range"] = outside
    grouped["transfer_status"] = np.select([~angle_ok, outside, grouped.n_release_pitches < 100],
                                            ["invalid_model_prediction", "outside_MLB_training_range", "small_sample_unvalidated_KBO"],
                                            default="MLB_transfer_unvalidated_KBO")
    return grouped


def run(reference_path: Path, pitch_path: Path, output: Path):
    source = pd.read_csv(reference_path, dtype={"pitcher": str})
    reference, excluded = prepare_reference(source)
    model, report, oof = fit_reference(reference)
    pitches = pd.read_parquet(pitch_path)
    predictions = transfer(model, reference, pitches)
    output.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(output / "kbo_calibrated_pitchers.csv", index=False)
    oof.to_csv(output / "mlb_cross_validation.csv", index=False)
    report.update({"excluded_reference_rows": excluded,
                   "kbo_season_estimates": int(predictions.mlb_calibrated_season_angle_deg.notna().sum()),
                   "kbo_transfer_statuses": {str(k): int(v) for k, v in predictions.transfer_status.value_counts().items()},
                   "input_hashes": {"reference": digest(reference_path), "pitches": digest(pitch_path), "implementation": digest(Path(__file__))},
                   "height_scenario_assumptions": asdict(Assumptions())})
    (output / "calibration_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n")
    print(json.dumps({k: report[k] for k in ("reference_rows", "reference_pitchers", "model_oof", "fixed_130cm_baseline", "height_scenario_baseline", "kbo_season_estimates")}, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=Path(".cache/arm_angle/mlb_reference.csv"))
    parser.add_argument("--pitches", type=Path, default=Path(".cache/arm_angle/pitches.parquet"))
    parser.add_argument("--out", type=Path, default=Path(".cache/arm_angle"))
    args = parser.parse_args()
    run(args.reference, args.pitches, args.out)


if __name__ == "__main__":
    main()
