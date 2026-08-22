"""Experimental KBO catcher Blocks Above Average model and web export."""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha1
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq


PITCH_TYPES = ("FF", "FT", "SI", "FC", "SL", "ST", "CU", "CH", "FS", "UN")
CONTINUOUS = (
    "px", "pz", "velocity_kmh", "vertical_movement_cm", "horizontal_movement_cm",
    "drop_angle", "arrival_time_s", "x0", "y0", "z0", "below_zone", "side_zone",
    "center_distance", "runner_count", "two_strikes",
)
QUALIFIED_OPPORTUNITIES = 500


def _number(value: Any) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else math.nan
    except (TypeError, ValueError):
        return math.nan


def _opportunity(row: dict[str, Any]) -> bool:
    return (
        row.get("is_wild_pitch") is not None
        and row.get("is_passed_ball") is not None
        and bool(row.get("catcher_id"))
        and str(row.get("pitch_call_code", "")) not in {"F", "X"}
        and (int(row.get("base_state_code_before") or 0) != 0 or int(row.get("strikes_before") or 0) == 2)
        and math.isfinite(_number(row.get("px")))
        and math.isfinite(_number(row.get("pz")))
    )


def _feature_rows(rows: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    raw: list[list[float]] = []
    for row in rows:
        px, pz = _number(row.get("px")), _number(row.get("pz"))
        sz_bottom = _number(row.get("sz_bottom"))
        runners = sum(bool(row.get(base)) for base in ("runner_1b_id_before", "runner_2b_id_before", "runner_3b_id_before"))
        values = [
            px, pz, _number(row.get("velocity_kmh")), _number(row.get("vertical_movement_cm")),
            _number(row.get("horizontal_movement_cm")), _number(row.get("drop_angle")),
            _number(row.get("arrival_time_s")), _number(row.get("x0")), _number(row.get("y0")), _number(row.get("z0")),
            max(0.0, sz_bottom - pz) if math.isfinite(sz_bottom) else max(0.0, 1.5 - pz),
            max(0.0, abs(px) - 0.83), math.sqrt((px / .83) ** 2 + ((pz - 2.5) / 1.0) ** 2),
            float(runners), float(int(row.get("strikes_before") or 0) == 2),
        ]
        pitch_type = str(row.get("pitch_type_code") or "UN")
        values.extend(float(pitch_type == code) for code in PITCH_TYPES)
        stance = str(row.get("batter_stance") or "")
        values.extend((float(stance == "L"), float(stance == "R")))
        x0 = _number(row.get("x0"))
        values.extend((float(math.isfinite(x0) and x0 < 0), float(math.isfinite(x0) and x0 >= 0)))
        raw.append(values)
    matrix = np.asarray(raw, dtype=float)
    continuous = matrix[:, :len(CONTINUOUS)]
    medians = np.nanmedian(continuous, axis=0)
    medians = np.where(np.isfinite(medians), medians, 0.0)
    missing = ~np.isfinite(continuous)
    continuous[missing] = np.take(medians, np.where(missing)[1])
    scales = continuous.std(axis=0)
    scales[scales < 1e-9] = 1.0
    continuous[:] = (continuous - continuous.mean(axis=0)) / scales
    target = np.asarray([float(bool(row.get("is_wild_pitch")) or bool(row.get("is_passed_ball"))) for row in rows])
    return matrix, target


def _fit_logistic(x: np.ndarray, y: np.ndarray, iterations: int = 180, l2: float = .002) -> tuple[np.ndarray, float]:
    features = x.shape[1]
    beta, first, second = np.zeros(features), np.zeros(features), np.zeros(features)
    prevalence = min(.25, max(1e-5, float(y.mean())))
    intercept = math.log(prevalence / (1.0 - prevalence))
    first_i = second_i = 0.0
    for step in range(1, iterations + 1):
        logits = np.clip(x @ beta + intercept, -24, 24)
        probabilities = 1.0 / (1.0 + np.exp(-logits))
        error = probabilities - y
        grad = (x.T @ error) / len(y) + l2 * beta
        grad_i = float(error.mean())
        first = .9 * first + .1 * grad; second = .999 * second + .001 * grad * grad
        first_i = .9 * first_i + .1 * grad_i; second_i = .999 * second_i + .001 * grad_i * grad_i
        rate = .025
        beta -= rate * (first / (1 - .9 ** step)) / (np.sqrt(second / (1 - .999 ** step)) + 1e-8)
        intercept -= rate * (first_i / (1 - .9 ** step)) / (math.sqrt(second_i / (1 - .999 ** step)) + 1e-8)
    return beta, intercept


def _cross_fitted_probabilities(rows: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    x, target = _feature_rows(rows)
    folds = np.asarray([int(sha1(str(row.get("game_id", "")).encode()).hexdigest()[:8], 16) % 5 for row in rows])
    probabilities = np.zeros(len(rows))
    for fold in range(5):
        train, test = folds != fold, folds == fold
        if not test.any():
            continue
        if train.sum() < 100 or target[train].sum() < 2:
            probabilities[test] = target[train].mean() if train.any() else target.mean()
            continue
        beta, intercept = _fit_logistic(x[train], target[train])
        probabilities[test] = 1.0 / (1.0 + np.exp(-np.clip(x[test] @ beta + intercept, -24, 24)))
    return np.clip(probabilities, .0001, .75), target


def _difficulty(probability: float) -> str:
    if probability <= .05:
        return "easy"
    if probability <= .15:
        return "medium"
    return "tough"


def _round(value: float, digits: int = 2) -> float:
    return round(float(value), digits)


def _auc(probabilities: np.ndarray, target: np.ndarray) -> float:
    positives = int(target.sum()); negatives = len(target) - positives
    if not positives or not negatives:
        return math.nan
    order = np.argsort(probabilities, kind="stable")
    ranks = np.empty(len(target), dtype=float); ranks[order] = np.arange(1, len(target) + 1)
    return float((ranks[target == 1].sum() - positives * (positives + 1) / 2) / (positives * negatives))


def build_blocking(root: Path, season: int = 2026, source_root: Path | None = None) -> Path:
    """Build cross-fitted BAA results and browser-friendly JSON."""
    source_root = source_root or root
    pitch_path = source_root / "data" / "processed" / "pitches.parquet"
    game_path = source_root / "data" / "processed" / "games.parquet"
    pitches = pq.read_table(pitch_path).to_pylist() if pitch_path.exists() else []
    games = pq.read_table(game_path).to_pylist() if game_path.exists() else []
    game_lookup = {str(game.get("game_id")): game for game in games}
    opportunities = [row for row in pitches if int(row.get("season") or season) == season and _opportunity(row)]
    output = root / "web" / "data" / "blocking" / str(season)
    output.mkdir(parents=True, exist_ok=True)
    if not opportunities:
        payload = {"schema_version": 1, "season": season, "status": "unavailable", "players": [], "details": {}}
        (output / "leaderboard.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return output / "leaderboard.json"

    probabilities, actual = _cross_fitted_probabilities(opportunities)
    detail_rows: list[dict[str, Any]] = []
    for row, probability, outcome in zip(opportunities, probabilities, actual):
        game = game_lookup.get(str(row.get("game_id")), {})
        catcher_team = game.get("home_team") if row.get("inning_half") == "top" else game.get("away_team")
        contribution = float(probability - outcome)
        detail_rows.append({
            "season": season, "game_id": row.get("game_id"), "pitch_id": row.get("pitch_id"),
            "catcher_id": str(row.get("catcher_id")), "catcher_name": row.get("catcher_name"), "team": catcher_team,
            "pitch_type_code": row.get("pitch_type_code"), "pitch_type_kr": row.get("pitch_type_kr"),
            "px": _number(row.get("px")), "pz": _number(row.get("pz")), "velocity_kmh": _number(row.get("velocity_kmh")),
            "expected_pbwp": float(probability), "actual_pbwp": int(outcome), "block_value": contribution,
            "difficulty": _difficulty(float(probability)),
        })

    processed = source_root / "data" / "processed" / "blocking_pitches.parquet"
    temporary = processed.with_suffix(".parquet.tmp")
    pq.write_table(pa.Table.from_pylist(detail_rows), temporary); temporary.replace(processed)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in detail_rows:
        grouped[row["catcher_id"]].append(row)
    players, details = [], {}
    for catcher_id, rows in grouped.items():
        opportunities_count = len(rows)
        expected = sum(row["expected_pbwp"] for row in rows)
        actual_count = sum(row["actual_pbwp"] for row in rows)
        baa = expected - actual_count
        difficulty_counts = {name: sum(row["difficulty"] == name for row in rows) for name in ("easy", "medium", "tough")}
        difficulty_values = {name: sum(row["block_value"] for row in rows if row["difficulty"] == name) for name in difficulty_counts}
        teams = sorted({str(row.get("team") or "") for row in rows if row.get("team")})
        player = {
            "catcher_id": catcher_id, "catcher_name": rows[0].get("catcher_name") or catcher_id,
            "team": "/".join(teams), "opportunities": opportunities_count,
            "blocking_runs": _round(baa * .25, 1), "baa": _round(baa, 1),
            "actual_pbwp": int(actual_count), "estimated_pbwp": _round(expected, 1),
            "baa_per_game": _round(baa / opportunities_count * 40, 2),
            "qualified": opportunities_count >= QUALIFIED_OPPORTUNITIES,
            "difficulty_pct": {name: _round(count / opportunities_count * 100, 1) for name, count in difficulty_counts.items()},
            "difficulty_baa": {name: _round(value, 1) for name, value in difficulty_values.items()},
        }
        players.append(player)
        cells: dict[tuple[int, int, str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            x_bin = max(-3, min(2, math.floor(row["px"] / .5)))
            z_bin = max(0, min(5, math.floor(row["pz"] / .75)))
            cells[(x_bin, z_bin, row["difficulty"], str(row.get("pitch_type_code") or "UN"))].append(row)
        details[catcher_id] = {
            "cells": [{"x": key[0], "z": key[1], "difficulty": key[2], "pitch_type": key[3], "opportunities": len(values), "baa": _round(sum(v["block_value"] for v in values), 2), "risk": _round(sum(v["expected_pbwp"] for v in values) / len(values), 4)} for key, values in sorted(cells.items())],
            "pitch_types": sorted({str(row.get("pitch_type_code") or "UN") for row in rows}),
        }
    players.sort(key=lambda row: (-row["baa"], -row["opportunities"], row["catcher_name"]))
    for rank, player in enumerate(players, 1):
        player["rank"] = rank
    payload = {
        "schema_version": 1, "season": season, "status": "experimental", "players": players, "details": details,
        "method": {
            "label": "KBO Blocks Above Average (experimental)",
            "opportunity": "Runner on base or two strikes; non-contact pitch with confirmed WP/PB coverage",
            "formula": "sum(estimated PB+WP probability - actual PB+WP)",
            "features": ["pitch location", "speed", "movement", "pitch type", "initial x/y/z position", "release side", "batter handedness", "base/strike state"],
            "missing_feature": "Catcher setup location is not available in the public KBO/VB source",
            "qualified_opportunities": QUALIFIED_OPPORTUNITIES,
            "difficulty": {"easy": "block probability >= 95%", "medium": "85-95%", "tough": "< 85%"},
            "runs_per_block": .25,
            "model": "Five-fold game-grouped cross-fitted logistic regression",
        },
        "summary": {
            "opportunities": len(detail_rows), "actual_pbwp": int(actual.sum()),
            "estimated_pbwp": _round(float(probabilities.sum()), 1), "catchers": len(players),
            "auc": _round(_auc(probabilities, actual), 3),
            "brier": _round(float(np.mean((probabilities - actual) ** 2)), 5),
        },
    }
    (output / "leaderboard.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return output / "leaderboard.json"
