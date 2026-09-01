"""Build research tables for KBO hitter swing-decision analysis.

This module intentionally exports ingredients rather than declaring a final
all-in-one metric.  The player table contains transparent zone rates, OLS
residuals, and unsupervised profile clusters that can be reviewed before any
post-hoc adjustment is adopted.
"""
from __future__ import annotations

from collections import defaultdict
import csv
import json
import math
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

MIN_PITCHES = 300
OUTLIER_Z = 1.5
CLUSTER_FEATURES = (
    "heart_vs_chase_residual",
    "shadow_in_swing_pct",
    "shadow_out_swing_pct",
    "waste_swing_pct",
    "z_contact_pct",
    "o_contact_pct",
)


def _pct(numerator: int | float, denominator: int | float) -> float | None:
    return round(100 * numerator / denominator, 4) if denominator else None


def _mean(values: list[float]) -> float | None:
    return round(float(np.mean(values)), 6) if values else None


def _zone(row: dict) -> str:
    distance = max(abs(float(row["x_relative"])), abs(float(row["z_relative"])))
    if distance <= 2 / 3:
        return "heart"
    if distance <= 1:
        return "shadow_in"
    if distance <= 4 / 3:
        return "shadow_out"
    if distance <= 2:
        return "chase"
    return "waste"


def _compact_pitch(row: dict) -> dict:
    zone = _zone(row)
    in_zone = zone in {"heart", "shadow_in"}
    swing = row.get("decision_type") == "Swing"
    contact = bool(row.get("is_contact"))
    return {
        "season": int(row["season"]),
        "game_date": row.get("game_date"),
        "game_id": row.get("game_id"),
        "pa_id": row.get("pa_id"),
        "pitch_id": row.get("pitch_id"),
        "batter_id": str(row.get("batter_id") or ""),
        "batter_name": str(row.get("batter_name") or ""),
        "batter_stance": row.get("batter_stance"),
        "pitcher_id": str(row.get("pitcher_id") or ""),
        "pitch_type": row.get("pitch_type"),
        "balls": int(row["balls_before"]),
        "strikes": int(row["strikes_before"]),
        "x_relative": float(row["x_relative"]),
        "z_relative": float(row["z_relative"]),
        "zone": zone,
        "in_zone": in_zone,
        "swing": swing,
        "take": not swing,
        "contact": contact,
        "whiff": swing and not contact,
        "simple_correct_decision": (swing and in_zone) or (not swing and not in_zone),
        "observed_decision_run": float(row.get("decision_run") or 0),
    }


def _player_row(items: list[dict]) -> dict:
    first = items[0]
    zones = defaultdict(list)
    for item in items:
        zones[item["zone"]].append(item)
    swings = [item for item in items if item["swing"]]
    contacts = [item for item in swings if item["contact"]]
    in_zone = [item for item in items if item["in_zone"]]
    out_zone = [item for item in items if not item["in_zone"]]
    z_swings = [item for item in in_zone if item["swing"]]
    o_swings = [item for item in out_zone if item["swing"]]
    zone_takes = len(in_zone) - len(z_swings)
    out_takes = len(out_zone) - len(o_swings)
    selection_tendency = _pct(out_takes, len(z_swings) + out_takes)
    hittable_take = _pct(zone_takes, zone_takes + out_takes)

    def zone_swing_pct(name: str) -> float | None:
        values = zones[name]
        return _pct(sum(item["swing"] for item in values), len(values))

    z_swing = _pct(len(z_swings), len(in_zone))
    o_swing = _pct(len(o_swings), len(out_zone))
    heart_swing = zone_swing_pct("heart")
    return {
        "season": first["season"],
        "batter_id": first["batter_id"],
        "batter_name": first["batter_name"],
        "batter_stance": first["batter_stance"],
        "pitches_seen": len(items),
        "plate_appearances": len({item["pa_id"] for item in items}),
        "qualified_300": len(items) >= MIN_PITCHES,
        "swing_pct": _pct(len(swings), len(items)),
        "take_pct": _pct(len(items) - len(swings), len(items)),
        "zone_pct": _pct(len(in_zone), len(items)),
        "z_swing_pct": z_swing,
        "o_swing_pct": o_swing,
        "z_minus_o_swing": round(z_swing - o_swing, 4) if z_swing is not None and o_swing is not None else None,
        "heart_swing_pct": heart_swing,
        "shadow_in_swing_pct": zone_swing_pct("shadow_in"),
        "shadow_out_swing_pct": zone_swing_pct("shadow_out"),
        "chase_swing_pct": zone_swing_pct("chase"),
        "waste_swing_pct": zone_swing_pct("waste"),
        "heart_minus_chase_swing": round(heart_swing - zone_swing_pct("chase"), 4)
        if heart_swing is not None and zone_swing_pct("chase") is not None else None,
        "contact_pct": _pct(len(contacts), len(swings)),
        "whiff_pct": _pct(len(swings) - len(contacts), len(swings)),
        "z_contact_pct": _pct(sum(item["contact"] for item in z_swings), len(z_swings)),
        "o_contact_pct": _pct(sum(item["contact"] for item in o_swings), len(o_swings)),
        "simple_judgment_pct": _pct(sum(item["simple_correct_decision"] for item in items), len(items)),
        "seager_a_zone_swings": len(z_swings),
        "seager_b_out_swings": len(o_swings),
        "seager_c_zone_takes": zone_takes,
        "seager_d_out_takes": out_takes,
        "selection_tendency_pct": selection_tendency,
        "hittable_take_pct": hittable_take,
        "simple_seager": round(selection_tendency - hittable_take, 4)
        if selection_tendency is not None and hittable_take is not None else None,
        "observed_decision_run": round(sum(item["observed_decision_run"] for item in items), 6),
        "observed_decision_run_per_100": round(100 * sum(item["observed_decision_run"] for item in items) / len(items), 6),
        "heart_pitches": len(zones["heart"]),
        "shadow_in_pitches": len(zones["shadow_in"]),
        "shadow_out_pitches": len(zones["shadow_out"]),
        "chase_pitches": len(zones["chase"]),
        "waste_pitches": len(zones["waste"]),
    }


def _ols(rows: list[dict], name: str, x_name: str, y_name: str, residual_name: str | None = None) -> dict:
    usable = [row for row in rows if row.get(x_name) is not None and row.get(y_name) is not None]
    x = np.array([row[x_name] for row in usable], dtype=float)
    y = np.array([row[y_name] for row in usable], dtype=float)
    if len(usable) < 3 or np.isclose(np.var(x), 0):
        return {"name": name, "x": x_name, "y": y_name, "n": len(usable), "available": False}
    slope, intercept = np.polyfit(x, y, 1)
    fitted = intercept + slope * x
    residuals = y - fitted
    r_squared = 1 - float(np.sum(residuals ** 2) / np.sum((y - y.mean()) ** 2)) if not np.isclose(np.var(y), 0) else 0.0
    if residual_name:
        for row, residual in zip(usable, residuals):
            row[residual_name] = round(float(residual), 6)
    return {
        "name": name,
        "x": x_name,
        "y": y_name,
        "n": len(usable),
        "available": True,
        "intercept": round(float(intercept), 8),
        "slope": round(float(slope), 8),
        "r_squared": round(r_squared, 8),
    }


def _kmeans(matrix: np.ndarray, k: int, iterations: int = 100) -> tuple[np.ndarray, np.ndarray]:
    """Small deterministic k-means implementation to avoid a runtime dependency."""
    order = np.argsort(matrix[:, 0])
    seeds = np.linspace(0, len(order) - 1, k).round().astype(int)
    centroids = matrix[order[seeds]].copy()
    labels = np.zeros(len(matrix), dtype=int)
    for _ in range(iterations):
        distances = ((matrix[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
        next_labels = distances.argmin(axis=1)
        next_centroids = np.array([
            matrix[next_labels == cluster].mean(axis=0) if np.any(next_labels == cluster) else centroids[cluster]
            for cluster in range(k)
        ])
        if np.array_equal(labels, next_labels) and np.allclose(centroids, next_centroids):
            break
        labels, centroids = next_labels, next_centroids
    return labels, centroids


def _cluster(rows: list[dict]) -> dict:
    usable = [row for row in rows if all(row.get(feature) is not None for feature in CLUSTER_FEATURES)]
    if len(usable) < 8:
        return {"available": False, "n": len(usable), "features": list(CLUSTER_FEATURES)}
    raw = np.array([[row[feature] for feature in CLUSTER_FEATURES] for row in usable], dtype=float)
    means, stds = raw.mean(axis=0), raw.std(axis=0)
    stds[stds == 0] = 1
    standardized = (raw - means) / stds
    k = min(4, max(2, len(usable) // 20 + 2))
    labels, centroids = _kmeans(standardized, k)
    for row, label, vector in zip(usable, labels, standardized):
        row["cluster_id"] = int(label) + 1
        row["cluster_distance"] = round(float(np.linalg.norm(vector - centroids[label])), 6)
    return {
        "available": True,
        "n": len(usable),
        "k": k,
        "features": list(CLUSTER_FEATURES),
        "standardization": {
            feature: {"mean": round(float(mean), 6), "std": round(float(std), 6)}
            for feature, mean, std in zip(CLUSTER_FEATURES, means, stds)
        },
        "centroids_z": [
            {feature: round(float(value), 6) for feature, value in zip(CLUSTER_FEATURES, centroid)}
            for centroid in centroids
        ],
        "sizes": {str(cluster + 1): int(np.sum(labels == cluster)) for cluster in range(k)},
    }


def _mark_outliers(rows: list[dict], fields: tuple[str, ...]) -> None:
    for field in fields:
        values = np.array([row[field] for row in rows if row.get(field) is not None], dtype=float)
        if not len(values) or np.isclose(values.std(), 0):
            continue
        mean, std = values.mean(), values.std()
        for row in rows:
            if row.get(field) is None:
                continue
            z = (row[field] - mean) / std
            row[f"{field}_z"] = round(float(z), 6)
            row[f"{field}_outlier"] = abs(z) >= OUTLIER_Z


def build_plate_discipline(root: Path, season: int = 2026, source: Path | None = None) -> tuple[int, int]:
    """Export pitch/player research tables, regression metadata, and clusters."""
    source = source or root / "data" / "processed" / "decision_pitches.parquet"
    raw_rows = pq.read_table(source).to_pylist()
    compact = [
        _compact_pitch(row) for row in raw_rows
        if row.get("season") == season
        and row.get("decision_type") in {"Swing", "Take"}
        and row.get("x_relative") is not None
        and row.get("z_relative") is not None
        and row.get("batter_name")
    ]
    by_batter = defaultdict(list)
    for row in compact:
        by_batter[(row["batter_id"], row["batter_name"])].append(row)
    players = [_player_row(items) for _, items in sorted(by_batter.items(), key=lambda item: item[0][1])]
    qualified = [row for row in players if row["qualified_300"]]
    derived_fields = (
        "heart_vs_chase_residual", "zone_vs_out_residual", "decision_run_residual",
        "heart_vs_chase_residual_z", "zone_vs_out_residual_z", "decision_run_residual_z",
        "heart_vs_chase_residual_outlier", "zone_vs_out_residual_outlier", "decision_run_residual_outlier",
        "cluster_id", "cluster_distance",
    )
    for row in players:
        for field in derived_fields:
            row[field] = None

    regressions = [
        _ols(qualified, "heart swing vs chase swing", "chase_swing_pct", "heart_swing_pct", "heart_vs_chase_residual"),
        _ols(qualified, "zone swing vs out-of-zone swing", "o_swing_pct", "z_swing_pct", "zone_vs_out_residual"),
        _ols(qualified, "observed decision run vs selective aggression", "heart_minus_chase_swing", "observed_decision_run_per_100", "decision_run_residual"),
        _ols(qualified, "observed decision run vs simple judgment", "simple_judgment_pct", "observed_decision_run_per_100"),
        _ols(qualified, "observed decision run vs Simple SEAGER", "simple_seager", "observed_decision_run_per_100"),
    ]
    _mark_outliers(qualified, ("heart_vs_chase_residual", "zone_vs_out_residual", "decision_run_residual"))
    clusters = _cluster(qualified)

    processed = root / "data" / "processed"
    exports = root / "exports"
    processed.mkdir(parents=True, exist_ok=True)
    exports.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(compact), processed / "plate_discipline_pitches.parquet")
    pq.write_table(pa.Table.from_pylist(players), processed / "plate_discipline_batters.parquet")
    csv_path = exports / f"plate_discipline_research_{season}.csv"
    fieldnames = list(players[0]) if players else []
    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(players)

    metadata = {
        "schema_version": 1,
        "season": season,
        "source": str(source.relative_to(root)) if source.is_relative_to(root) else str(source),
        "pitches": len(compact),
        "batters": len(players),
        "qualified_batters": len(qualified),
        "minimum_pitches": MIN_PITCHES,
        "zone_contract": {
            "coordinates": "Visual Baseball ABS px/pz normalized to each pitch's sz_top/sz_bottom; plate half-width 10/12 ft",
            "distance": "max(abs(x_relative), abs(z_relative))",
            "heart": "0–66.7%",
            "shadow_in": "66.7–100%",
            "shadow_out": "100–133.3%",
            "chase": "133.3–200%",
            "waste": ">200%",
        },
        "metric_notes": {
            "simple_judgment_pct": "Swing in the rule-book zone or take outside it; intentionally binary and outcome-free.",
            "simple_seager": "100 × [D/(A+D) - C/(C+D)], where A=zone swing, B=out-of-zone swing, C=zone take, D=out-of-zone take.",
            "observed_decision_run": "Existing RE288 location/count-neutral observed result. It is diagnostic, not a counterfactual swing-versus-take value.",
            "clusters": "Unsupervised profile groups on standardized qualified-hitter features. Cluster numbers are not ordered grades.",
        },
        "limitations": [
            "Visual Baseball does not provide exit velocity or launch angle, so hittable-pitch quality cannot yet be individualized like a full PLV model.",
            "Observed swing/take outcomes are subject to selection bias; the unchosen action is not observed.",
            "Cluster labels are deliberately left numeric until baseball interpretation is reviewed.",
        ],
        "regressions": regressions,
        "clustering": clusters,
    }
    (processed / "plate_discipline_research.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return len(compact), len(players)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--source")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    pitches, batters = build_plate_discipline(root, args.season, Path(args.source).resolve() if args.source else None)
    print(f"exported {pitches} decision pitches and {batters} batter profiles")
