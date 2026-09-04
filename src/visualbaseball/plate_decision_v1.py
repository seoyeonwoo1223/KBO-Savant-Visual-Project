"""Cross-fitted KBO swing-decision research metrics.

The public outputs are deliberately limited to Swing Aggression, neutral Zone
Awareness (raw and percentile), and Decision Value per 100 pitches.  Supporting
rates, regressions, residuals, and clusters are diagnostics only.
"""
from __future__ import annotations

from collections import defaultdict
import csv
import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from sklearn.cluster import KMeans
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score, silhouette_score
from sklearn.model_selection import GroupKFold

from .pitch_arsenal import PARK_FACTOR_CODE, _load_park_factors, _pitch_code, _stadium
from .zone_awareness_v2 import _team_history


MIN_PITCHES = 300
N_SPLITS = 5
RANDOM_STATE = 20260903
OUTLIER_Z = 2.0
REGIONS = ("heart", "shadow", "chase", "waste")

BASE_NUMERIC = (
    "x_relative", "z_relative", "balls_before", "strikes_before", "outs_before",
    "base_state_code_before", "velocity_kmh", "release_height_cm",
)
MOVEMENT_NUMERIC = ("adjusted_hb_cm", "adjusted_ivb_cm")
CATEGORICAL = ("pitch_type", "batter_stance", "stadium")
PZONE_NUMERIC = ("x_relative", "z_relative", "sz_top", "sz_bottom")


def _classifier(categorical_start: int | None = None) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        learning_rate=0.07, max_iter=130, max_leaf_nodes=20,
        min_samples_leaf=80, l2_regularization=1.5, random_state=RANDOM_STATE,
        categorical_features=(list(range(categorical_start, categorical_start + len(CATEGORICAL)))
                              if categorical_start is not None else None),
    )


def _regressor(categorical_start: int) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        learning_rate=0.06, max_iter=130, max_leaf_nodes=18,
        min_samples_leaf=80, l2_regularization=2.0, random_state=RANDOM_STATE,
        categorical_features=list(range(categorical_start, categorical_start + len(CATEGORICAL))),
    )


def _safe_float(value) -> float:
    try:
        value = float(value)
        return value if np.isfinite(value) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _encode(rows: list[dict], numeric: tuple[str, ...]) -> tuple[np.ndarray, dict]:
    columns = [np.array([_safe_float(row.get(field)) for row in rows]) for field in numeric]
    mappings = {}
    for field in CATEGORICAL:
        values = sorted({str(row.get(field) or "") for row in rows})
        mapping = {value: index for index, value in enumerate(values)}
        mappings[field] = mapping
        columns.append(np.array([mapping[str(row.get(field) or "")] for row in rows], dtype=float))
    return np.column_stack(columns), mappings


def _encode_numeric(rows: list[dict], fields: tuple[str, ...]) -> np.ndarray:
    return np.column_stack([
        np.array([_safe_float(row.get(field)) for row in rows], dtype=float) for field in fields
    ])


def _movement_adjust(rows: list[dict], root: Path, season: int) -> dict:
    factors = _load_park_factors(root, season)
    available = adjusted = 0
    for row in rows:
        hb = _safe_float(row.get("horizontal_movement_cm"))
        ivb = _safe_float(row.get("vertical_movement_cm"))
        row["adjusted_hb_cm"], row["adjusted_ivb_cm"] = np.nan, np.nan
        if np.isnan(hb) or np.isnan(ivb):
            continue
        available += 1
        code = PARK_FACTOR_CODE.get(_pitch_code(row), _pitch_code(row))
        offset = factors.get((_stadium(row.get("stadium")), code))
        if offset is None:
            continue
        row["adjusted_hb_cm"] = hb + offset[0]
        row["adjusted_ivb_cm"] = ivb + offset[1]
        adjusted += 1
    return {
        "movement_available": available,
        "movement_adjusted": adjusted,
        "adjustment_coverage_pct": round(100 * adjusted / available, 4) if available else 0.0,
        "formula": "adjusted movement = Visual Baseball measurement + stadium/pitch offset",
    }


def _valid_rows(source: Path, season: int) -> tuple[list[dict], dict]:
    rows, excluded = [], defaultdict(int)
    for row in pq.read_table(source).to_pylist():
        if int(row.get("season") or season) != season:
            excluded["other_season"] += 1
            continue
        if row.get("decision_type") not in {"Swing", "Take"}:
            excluded["unsupported_action"] += 1
            continue
        required = ("x_relative", "z_relative", "raw_run_value", "game_id", "batter_id", "batter_name")
        if any(row.get(field) is None or row.get(field) == "" for field in required):
            excluded["missing_required"] += 1
            continue
        rows.append(row)
    return rows, dict(excluded)


def _crossfit_probability(
    matrix: np.ndarray, target: np.ndarray, groups: np.ndarray, categorical_start: int,
) -> np.ndarray:
    result = np.full(len(target), np.nan)
    for train, test in GroupKFold(N_SPLITS).split(matrix, target, groups):
        model = _classifier(categorical_start).fit(matrix[train], target[train])
        result[test] = model.predict_proba(matrix[test])[:, list(model.classes_).index(1)]
    return np.clip(result, 1e-6, 1 - 1e-6)


def _crossfit_pzone(rows: list[dict], groups: np.ndarray) -> np.ndarray:
    matrix = _encode_numeric(rows, PZONE_NUMERIC)
    is_take = np.array([row["decision_type"] == "Take" for row in rows])
    called_strike = np.array([str(row.get("pitch_call_code") or "").upper() == "T" for row in rows], dtype=int)
    result = np.full(len(rows), np.nan)
    splitter = GroupKFold(N_SPLITS)
    for train, test in splitter.split(matrix, np.zeros(len(rows)), groups):
        take_train = train[is_take[train]]
        model = _classifier().fit(matrix[take_train], called_strike[take_train])
        result[test] = model.predict_proba(matrix[test])[:, list(model.classes_).index(1)]
    return np.clip(result, 1e-6, 1 - 1e-6)


def _crossfit_action_values(
    matrix: np.ndarray, actions: np.ndarray, target: np.ndarray, groups: np.ndarray,
    categorical_start: int,
) -> tuple[np.ndarray, np.ndarray]:
    swing_value, take_value = np.full(len(actions), np.nan), np.full(len(actions), np.nan)
    for train, test in GroupKFold(N_SPLITS).split(matrix, actions, groups):
        swing_train, take_train = train[actions[train] == 1], train[actions[train] == 0]
        swing_model = _regressor(categorical_start).fit(matrix[swing_train], target[swing_train])
        take_model = _regressor(categorical_start).fit(matrix[take_train], target[take_train])
        swing_value[test] = swing_model.predict(matrix[test])
        take_value[test] = take_model.predict(matrix[test])
    return swing_value, take_value


def _bootstrap_logloss_improvement(
    y: np.ndarray, p_x: np.ndarray, p_o: np.ndarray, groups: np.ndarray, iterations: int = 1000,
) -> tuple[float, float]:
    losses_x = -(y * np.log(p_x) + (1 - y) * np.log(1 - p_x))
    losses_o = -(y * np.log(p_o) + (1 - y) * np.log(1 - p_o))
    deltas = losses_x - losses_o
    unique = np.unique(groups)
    group_sums = np.array([deltas[groups == group].sum() for group in unique])
    group_counts = np.array([(groups == group).sum() for group in unique])
    rng = np.random.default_rng(RANDOM_STATE)
    selected = rng.integers(0, len(unique), size=(iterations, len(unique)))
    samples = group_sums[selected].sum(axis=1) / group_counts[selected].sum(axis=1)
    low, high = np.quantile(samples, [0.025, 0.975])
    return float(low), float(high)


def _model_metrics(y: np.ndarray, probability: np.ndarray) -> dict:
    return {
        "log_loss": round(float(log_loss(y, probability)), 8),
        "brier": round(float(brier_score_loss(y, probability)), 8),
        "roc_auc": round(float(roc_auc_score(y, probability)), 8),
        "mean_expected_swing_pct": round(float(100 * probability.mean()), 6),
        "sd_expected_swing_pct": round(float(100 * probability.std()), 6),
    }


def _region(row: dict) -> str:
    distance = max(abs(float(row["x_relative"])), abs(float(row["z_relative"])))
    if distance <= 2 / 3:
        return "heart"
    if distance <= 4 / 3:
        return "shadow"
    if distance <= 2:
        return "chase"
    return "waste"


def _pct(items: list[dict], predicate) -> float | None:
    return round(100 * sum(predicate(item) for item in items) / len(items), 6) if items else None


def _ols(rows: list[dict], x_field: str, y_field: str, residual_field: str | None = None) -> dict:
    usable = [row for row in rows if row.get(x_field) is not None and row.get(y_field) is not None]
    x = np.array([row[x_field] for row in usable], dtype=float)
    y = np.array([row[y_field] for row in usable], dtype=float)
    if len(usable) < 3 or np.isclose(x.var(), 0):
        return {"x": x_field, "y": y_field, "n": len(usable), "available": False}
    slope, intercept = np.polyfit(x, y, 1)
    fitted = intercept + slope * x
    residual = y - fitted
    r2 = 0.0 if np.isclose(y.var(), 0) else 1 - float((residual ** 2).sum() / ((y - y.mean()) ** 2).sum())
    if residual_field:
        for row, value in zip(usable, residual):
            row[residual_field] = round(float(value), 6)
    return {
        "x": x_field, "y": y_field, "n": len(usable), "available": True,
        "pearson_r": round(float(np.corrcoef(x, y)[0, 1]), 8),
        "r_squared": round(r2, 8), "slope": round(float(slope), 8),
        "intercept": round(float(intercept), 8),
    }


def _rank(values: list[float]) -> list[int]:
    order = np.argsort(-np.asarray(values), kind="stable")
    ranks = np.empty(len(values), dtype=int)
    ranks[order] = np.arange(1, len(values) + 1)
    return ranks.tolist()


def _player_tables(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[(str(row["batter_id"]), str(row["batter_name"]))].append(row)
    players, movement = [], []
    for (_, _), items in sorted(grouped.items(), key=lambda pair: pair[0][1]):
        first, n = items[0], len(items)
        in_zone = [item for item in items if abs(float(item["x_relative"])) <= 1 and abs(float(item["z_relative"])) <= 1]
        out_zone = [item for item in items if not (abs(float(item["x_relative"])) <= 1 and abs(float(item["z_relative"])) <= 1)]
        by_region = {region: [item for item in items if item["region"] == region] for region in REGIONS}
        meatball = [item for item in items if max(abs(float(item["x_relative"])), abs(float(item["z_relative"]))) <= 1 / 3]
        swing_pct = _pct(items, lambda item: item["swing"] == 1)
        z_swing = _pct(in_zone, lambda item: item["swing"] == 1)
        o_swing = _pct(out_zone, lambda item: item["swing"] == 1)
        player = {
            "season": int(first["season"]), "batter_id": str(first["batter_id"]),
            "batter_name": str(first["batter_name"]), "team": _team_history(items),
            "batter_stance": first.get("batter_stance"), "pitches_seen": n,
            "qualified_300": n >= MIN_PITCHES,
            "swing_aggression": round(100 * float(np.mean([item["swing"] - item["p_swing"] for item in items])), 6),
            "za_raw": round(100 * float(np.mean([item["za"] for item in items])), 6),
            "za_percentile": None,
            "dv_per_100": round(100 * float(np.mean([item["dv"] for item in items])), 6),
            "swing_pct": swing_pct, "z_swing_pct": z_swing, "o_swing_pct": o_swing,
            "z_minus_o_swing": round(z_swing - o_swing, 6) if z_swing is not None and o_swing is not None else None,
            "heart_swing_pct": _pct(by_region["heart"], lambda item: item["swing"] == 1),
            "meatball_swing_pct": _pct(meatball, lambda item: item["swing"] == 1),
            "shadow_swing_pct": _pct(by_region["shadow"], lambda item: item["swing"] == 1),
            "chase_swing_pct": _pct(by_region["chase"], lambda item: item["swing"] == 1),
            "waste_swing_pct": _pct(by_region["waste"], lambda item: item["swing"] == 1),
        }
        players.append(player)
        movement.append({
            "season": int(first["season"]), "batter_id": str(first["batter_id"]),
            "batter_name": str(first["batter_name"]), "team": player["team"], "pitches_seen": n,
            "qualified_300": n >= MIN_PITCHES,
            "actual_swing_pct": swing_pct,
            "expected_swing_x_pct": round(100 * float(np.mean([item["p_swing_x"] for item in items])), 6),
            "expected_swing_o_pct": round(100 * float(np.mean([item["p_swing_o"] for item in items])), 6),
        })
    qualified = [row for row in players if row["qualified_300"]]
    za_values = np.array([row["za_raw"] for row in qualified])
    for row in players:
        row["za_percentile"] = round(100 * (np.sum(za_values < row["za_raw"]) + 0.5 * np.sum(za_values == row["za_raw"])) / len(za_values), 3) if len(za_values) else None
    qualified_movement = [row for row in movement if row["qualified_300"]]
    ranks_x = _rank([row["expected_swing_x_pct"] for row in qualified_movement])
    ranks_o = _rank([row["expected_swing_o_pct"] for row in qualified_movement])
    for row, rank_x, rank_o in zip(qualified_movement, ranks_x, ranks_o):
        row["rank_x"], row["rank_o"], row["rank_change_o_minus_x"] = rank_x, rank_o, rank_o - rank_x
    return players, movement


def _diagnostics(players: list[dict]) -> tuple[list[dict], dict, list[dict]]:
    qualified = [row for row in players if row["qualified_300"]]
    residual_specs = (
        ("z_swing_pct", "z_swing_residual"), ("o_swing_pct", "o_swing_residual"),
        ("heart_swing_pct", "heart_swing_residual"), ("meatball_swing_pct", "meatball_swing_residual"),
        ("waste_swing_pct", "waste_swing_residual"), ("shadow_swing_pct", "shadow_swing_residual"),
    )
    regressions = [_ols(qualified, "za_raw", y, residual) for y, residual in residual_specs]
    regressions += [
        _ols(qualified, "swing_aggression", "swing_pct"),
        _ols(qualified, "za_raw", "dv_per_100"),
        _ols(qualified, "swing_aggression", "dv_per_100"),
    ]
    residual_fields = [residual for _, residual in residual_specs]
    matrix = np.array([[row[field] for field in residual_fields] for row in qualified], dtype=float)
    means, stds = matrix.mean(axis=0), matrix.std(axis=0)
    stds[stds == 0] = 1
    standardized = (matrix - means) / stds
    candidates = {}
    for k in range(2, min(6, len(qualified) - 1) + 1):
        labels = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=20).fit_predict(standardized)
        candidates[k] = float(silhouette_score(standardized, labels))
    best_k = max(candidates, key=candidates.get)
    model = KMeans(n_clusters=best_k, random_state=RANDOM_STATE, n_init=50).fit(standardized)
    distances = np.linalg.norm(standardized - model.cluster_centers_[model.labels_], axis=1)
    distance_cut = float(np.quantile(distances, 0.95))
    outliers = []
    for row, label, distance, vector in zip(qualified, model.labels_, distances, standardized):
        row["cluster_id"] = int(label) + 1
        row["cluster_distance"] = round(float(distance), 6)
        row["cluster_distance_outlier"] = bool(distance >= distance_cut)
        for field, z in zip(residual_fields, vector):
            row[f"{field}_z"] = round(float(z), 6)
        if distance >= distance_cut or np.any(np.abs(vector) >= OUTLIER_Z):
            outliers.append(row.copy())
    cluster_rows = []
    for cluster in range(best_k):
        members = [row for row in qualified if row.get("cluster_id") == cluster + 1]
        entry = {"cluster_id": cluster + 1, "players": len(members)}
        for field in residual_fields:
            entry[f"mean_{field}"] = round(float(np.mean([row[field] for row in members])), 6)
        entry["mean_za_raw"] = round(float(np.mean([row["za_raw"] for row in members])), 6)
        entry["mean_swing_aggression"] = round(float(np.mean([row["swing_aggression"] for row in members])), 6)
        entry["mean_swing_pct"] = round(float(np.mean([row["swing_pct"] for row in members])), 6)
        entry["mean_dv_per_100"] = round(float(np.mean([row["dv_per_100"] for row in members])), 6)
        cluster_rows.append(entry)
    joint_x = np.column_stack((
        np.ones(len(qualified)),
        np.array([row["za_raw"] for row in qualified]),
        np.array([row["swing_aggression"] for row in qualified]),
    ))
    joint_y = np.array([row["dv_per_100"] for row in qualified])
    coefficients = np.linalg.lstsq(joint_x, joint_y, rcond=None)[0]
    joint_residual = joint_y - joint_x @ coefficients
    total_ss = float(((joint_y - joint_y.mean()) ** 2).sum())
    joint_r2 = 1 - float((joint_residual ** 2).sum()) / total_ss if total_ss else 0.0
    cluster_residual_means = {}
    for cluster in range(1, best_k + 1):
        mask = np.array([row.get("cluster_id") == cluster for row in qualified])
        cluster_residual_means[str(cluster)] = round(float(joint_residual[mask].mean()), 6)
    metadata = {
        "features": residual_fields, "standardization": "qualified-batter z-scores",
        "selected_k": best_k, "selection": "maximum silhouette among k=2..6",
        "silhouette_by_k": {str(k): round(value, 6) for k, value in candidates.items()},
        "distance_outlier_threshold": "95th percentile within-cluster Euclidean distance",
        "residual_outlier_threshold": f"absolute residual z >= {OUTLIER_Z}",
        "clusters": cluster_rows,
        "dv_joint_diagnostic": {
            "formula": "DV/100 ~ intercept + ZA Raw + Swing Aggression",
            "intercept": round(float(coefficients[0]), 8),
            "za_coefficient": round(float(coefficients[1]), 8),
            "sa_coefficient": round(float(coefficients[2]), 8),
            "r_squared": round(joint_r2, 8),
            "mean_residual_by_cluster": cluster_residual_means,
            "interpretation": "Near-zero residual cluster means indicate the residual clusters add no material DV bias after ZA and SA.",
        },
    }
    return regressions, metadata, outliers


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_plate_decision_v1(root: Path, season: int = 2026, source: Path | None = None) -> dict:
    source = source or root / "data" / "processed" / (
        "decision_pitches.parquet" if season == 2026 else f"decision_pitches_{season}.parquet"
    )
    rows, excluded = _valid_rows(source, season)
    movement_meta = _movement_adjust(rows, root, season)
    actions = np.array([row["decision_type"] == "Swing" for row in rows], dtype=int)
    groups = np.array([str(row["game_id"]) for row in rows])
    rv = np.array([float(row["raw_run_value"]) for row in rows])
    matrix_x, _ = _encode(rows, BASE_NUMERIC)
    matrix_o, _ = _encode(rows, BASE_NUMERIC + MOVEMENT_NUMERIC)
    p_x = _crossfit_probability(matrix_x, actions, groups, len(BASE_NUMERIC))
    p_o = _crossfit_probability(matrix_o, actions, groups, len(BASE_NUMERIC + MOVEMENT_NUMERIC))
    metric_x, metric_o = _model_metrics(actions, p_x), _model_metrics(actions, p_o)
    ci_low, ci_high = _bootstrap_logloss_improvement(actions, p_x, p_o, groups)
    improvement = metric_x["log_loss"] - metric_o["log_loss"]
    selected = "Movement O" if improvement > 0 and ci_low > 0 else "Movement X"
    selected_matrix, selected_probability = (matrix_o, p_o) if selected == "Movement O" else (matrix_x, p_x)
    p_zone = _crossfit_pzone(rows, groups)
    selected_categorical_start = len(BASE_NUMERIC + MOVEMENT_NUMERIC) if selected == "Movement O" else len(BASE_NUMERIC)
    v_swing, v_take = _crossfit_action_values(selected_matrix, actions, rv, groups, selected_categorical_start)
    delta = v_swing - v_take
    za_judgment = np.where(actions == 1, p_zone, 1 - p_zone)
    za_expected = selected_probability * p_zone + (1 - selected_probability) * (1 - p_zone)
    za = za_judgment - za_expected
    dv = np.where(actions == 1, delta, -delta)
    pitch_output = []
    for index, source_row in enumerate(rows):
        row = dict(source_row)
        row.update({
            "region": _region(row), "swing": int(actions[index]),
            "adjusted_hb_cm": None if np.isnan(row["adjusted_hb_cm"]) else float(row["adjusted_hb_cm"]),
            "adjusted_ivb_cm": None if np.isnan(row["adjusted_ivb_cm"]) else float(row["adjusted_ivb_cm"]),
            "p_swing_x": float(p_x[index]), "p_swing_o": float(p_o[index]),
            "p_swing": float(selected_probability[index]), "p_zone": float(p_zone[index]),
            "zone_judgment": float(za_judgment[index]), "expected_zone_judgment": float(za_expected[index]),
            "za": float(za[index]), "v_swing": float(v_swing[index]), "v_take": float(v_take[index]),
            "delta_v": float(delta[index]), "dv": float(dv[index]),
        })
        pitch_output.append(row)
    players, movement_players = _player_tables(pitch_output)
    regressions, clustering, outliers = _diagnostics(players)
    processed, exports = root / "data" / "processed", root / "exports"
    processed.mkdir(parents=True, exist_ok=True)
    exports.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(pitch_output), processed / f"plate_decision_v1_pitches_{season}.parquet")
    pq.write_table(pa.Table.from_pylist(players), processed / f"plate_decision_v1_batters_{season}.parquet")
    _write_csv(exports / f"plate_decision_v1_players_{season}.csv", players)
    _write_csv(exports / f"plate_decision_v1_movement_comparison_{season}.csv", movement_players)
    _write_csv(exports / f"plate_decision_v1_outliers_{season}.csv", outliers)
    metadata = {
        "schema_version": 1, "season": season, "source": str(source.relative_to(root)),
        "pitches": len(rows), "batters": len(players),
        "qualified_batters": sum(row["qualified_300"] for row in players), "minimum_pitches": MIN_PITCHES,
        "cross_validation": f"{N_SPLITS}-fold GroupKFold by game_id; all displayed model predictions are out-of-fold",
        "movement": {
            **movement_meta, "x_features": list(BASE_NUMERIC) + list(CATEGORICAL),
            "o_features": list(BASE_NUMERIC + MOVEMENT_NUMERIC) + list(CATEGORICAL),
            "movement_x": metric_x, "movement_o": metric_o,
            "log_loss_improvement_x_minus_o": round(improvement, 8),
            "game_cluster_bootstrap_95pct_ci": [round(ci_low, 8), round(ci_high, 8)],
            "selection_rule": "Choose Movement O only when O lowers OOF log loss and the game-cluster bootstrap 95% CI excludes zero",
            "selected": selected,
        },
        "metrics": {
            "swing_aggression": "100 * mean(actual swing indicator - selected OOF expected swing probability); percentage points",
            "za_raw": "100 * mean(actual zone-aligned judgment - league expected judgment); percentage points",
            "za_percentile": "empirical percentile of ZA Raw among hitters with at least 300 pitches",
            "dv_per_100": "100 * mean((V_Swing - V_Take) for swings; sign reversed for takes); runs per 100 pitches",
        },
        "p_zone": {
            "target": "called strike vs ball/HBP among taken pitches",
            "features": list(PZONE_NUMERIC),
            "purpose": "smooth zone-aligned probability only; no run value or batted-ball outcome",
        },
        "base_stats": {
            "meatball": "max(abs(x_relative), abs(z_relative)) <= 1/3",
            "heart": "<= 2/3", "shadow": "> 2/3 and <= 4/3",
            "chase": "> 4/3 and <= 2", "waste": "> 2",
        },
        "regressions": regressions, "clustering": clustering, "excluded": excluded,
        "limitations": [
            "Counterfactual action values are observational conditional expectations; unmeasured pitch traits can leave selection bias.",
            "Visual Baseball lacks exit velocity and launch angle, so V_Swing estimates do not condition on contact quality measurements.",
            "Cluster labels diagnose model behavior and are not player grades or adjustment factors.",
        ],
    }
    (processed / f"plate_decision_v1_report_{season}.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return metadata


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--source")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    source = Path(args.source).resolve() if args.source else None
    print(json.dumps(build_plate_decision_v1(root, args.season, source), ensure_ascii=False, indent=2))
