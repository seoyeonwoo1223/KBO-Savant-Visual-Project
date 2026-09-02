"""Staged KBO Swing/Take Decision Value and Zone Awareness web exports."""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor


MIN_PITCHES = 300
GRID_STEP = 0.5
REGIONS = ("Heart", "Shadow", "Chase", "Waste")
NUMERIC_FEATURES = (
    "x_relative", "z_relative", "balls_before", "strikes_before", "outs_before",
    "base_state_code_before", "velocity_kmh", "horizontal_movement_cm",
    "vertical_movement_cm", "release_height_cm", "drop_angle",
)
CATEGORICAL_FEATURES = ("pitch_type", "batter_stance", "stadium")
SWING_OUTCOMES = ("Whiff", "Foul", "InPlay")
TAKE_OUTCOMES = ("Ball", "CalledStrike", "HBP")
OUTCOMES = SWING_OUTCOMES + TAKE_OUTCOMES
PROBABILITY_FIELDS = (
    "p_whiff_if_swing", "p_contact_if_swing", "p_foul_if_swing",
    "p_in_play_if_swing", "p_ball_if_take", "p_called_strike_if_take",
    "p_hbp_if_take",
)


def _region(row: dict) -> str:
    distance = max(abs(float(row["x_relative"])), abs(float(row["z_relative"])))
    if distance <= 2 / 3:
        return "Heart"
    if distance <= 4 / 3:
        return "Shadow"
    if distance <= 2:
        return "Chase"
    return "Waste"


def _outcome(row: dict) -> str | None:
    if row.get("decision_type") == "Swing":
        if not row.get("is_contact"):
            return "Whiff"
        return "InPlay" if row.get("is_in_play") else "Foul"
    if row.get("decision_type") == "Take":
        if row.get("is_pa_terminal") and (
            str(row.get("pa_type") or "").lower() == "hbp"
            or str(row.get("pa_result") or "") == "사구"
        ):
            return "HBP"
        code = str(row.get("pitch_call_code") or "").upper()
        if code == "T":
            return "CalledStrike"
        if code == "B":
            return "Ball"
    return None


def _categories(rows: list[dict]) -> dict[str, dict[str, int]]:
    return {
        field: {
            value: index for index, value in enumerate(
                sorted({str(row.get(field) or "") for row in rows})
            )
        }
        for field in CATEGORICAL_FEATURES
    }


def _matrix(rows: list[dict], categories: dict[str, dict[str, int]]) -> np.ndarray:
    columns = []
    for field in NUMERIC_FEATURES:
        columns.append(np.array([
            float(row[field]) if row.get(field) is not None else np.nan for row in rows
        ], dtype=float))
    for field in CATEGORICAL_FEATURES:
        mapping = categories[field]
        columns.append(np.array([
            mapping.get(str(row.get(field) or ""), 0) for row in rows
        ], dtype=float))
    return np.column_stack(columns)


def _classifier() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        learning_rate=0.08,
        max_iter=140,
        max_leaf_nodes=20,
        min_samples_leaf=60,
        l2_regularization=1.0,
        categorical_features=list(range(
            len(NUMERIC_FEATURES), len(NUMERIC_FEATURES) + len(CATEGORICAL_FEATURES)
        )),
        random_state=20260901,
    )


def _regressor() -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        learning_rate=0.08,
        max_iter=120,
        max_leaf_nodes=18,
        min_samples_leaf=40,
        l2_regularization=1.5,
        categorical_features=list(range(
            len(NUMERIC_FEATURES), len(NUMERIC_FEATURES) + len(CATEGORICAL_FEATURES)
        )),
        random_state=20260901,
    )


def _probability(model: HistGradientBoostingClassifier, matrix: np.ndarray, label) -> np.ndarray:
    return model.predict_proba(matrix)[:, list(model.classes_).index(label)]


def _fit_staged_models(rows: list[dict]) -> tuple[dict[str, np.ndarray], dict]:
    matrix = _matrix(rows, _categories(rows))
    actions = np.array([row["decision_type"] for row in rows])
    outcomes = np.array([row["model_outcome"] for row in rows])
    target = np.array([float(row["raw_run_value"]) for row in rows])

    swing_decision = _classifier()
    swing_decision.fit(matrix, actions == "Swing")
    p_swing = _probability(swing_decision, matrix, True)

    swing_mask = actions == "Swing"
    contact = _classifier()
    contact.fit(matrix[swing_mask], outcomes[swing_mask] != "Whiff")
    p_contact = _probability(contact, matrix, True)

    contact_mask = np.isin(outcomes, ("Foul", "InPlay"))
    in_play = _classifier()
    in_play.fit(matrix[contact_mask], outcomes[contact_mask] == "InPlay")
    p_in_play_given_contact = _probability(in_play, matrix, True)

    take_mask = actions == "Take"
    take_result = _classifier()
    take_result.fit(matrix[take_mask], outcomes[take_mask])
    take_probabilities = {
        name: _probability(take_result, matrix, name) for name in TAKE_OUTCOMES
    }

    branch_counts = Counter(outcomes)
    branch_rv = {}
    for outcome in OUTCOMES:
        mask = outcomes == outcome
        if int(mask.sum()) < 100:
            raise ValueError(f"{outcome} sample is too small: {int(mask.sum())}")
        model = _regressor()
        model.fit(matrix[mask], target[mask])
        branch_rv[outcome] = model.predict(matrix)

    p_whiff = 1 - p_contact
    p_foul = p_contact * (1 - p_in_play_given_contact)
    p_in_play = p_contact * p_in_play_given_contact
    expected_swing = (
        p_whiff * branch_rv["Whiff"]
        + p_foul * branch_rv["Foul"]
        + p_in_play * branch_rv["InPlay"]
    )
    expected_take = sum(
        take_probabilities[name] * branch_rv[name] for name in TAKE_OUTCOMES
    )
    predictions = {
        "expected_swing_probability": p_swing,
        "p_whiff_if_swing": p_whiff,
        "p_contact_if_swing": p_contact,
        "p_foul_if_swing": p_foul,
        "p_in_play_if_swing": p_in_play,
        "p_ball_if_take": take_probabilities["Ball"],
        "p_called_strike_if_take": take_probabilities["CalledStrike"],
        "p_hbp_if_take": take_probabilities["HBP"],
        "expected_swing_rv": expected_swing,
        "expected_take_rv": expected_take,
    }
    metadata = {
        "model": "Staged HistGradientBoosting outcome tree",
        "tree": {
            "swing": "Whiff / Contact; Contact -> Foul / InPlay",
            "take": "Ball / CalledStrike / HBP",
            "terminal_value": "Separate expected RE288 Run Value model for all six outcomes",
        },
        "features": list(NUMERIC_FEATURES) + list(CATEGORICAL_FEATURES),
        "branch_samples": {name: int(branch_counts[name]) for name in OUTCOMES},
    }
    return predictions, metadata


def _per_100(items: list[dict]) -> float | None:
    return round(100 * float(np.mean([item["decision_value"] for item in items])), 6) if items else None


def _standardize(players: list[dict], source: str, target: str) -> None:
    reference = [row[source] for row in players if row["qualified_300"] and row.get(source) is not None]
    mean = float(np.mean(reference)) if reference else 0.0
    std = float(np.std(reference)) or 1.0
    for row in players:
        value = row.get(source)
        row[target] = round(100 + 15 * (value - mean) / std, 3) if value is not None else None


def _player_rows(pitches: list[dict]) -> list[dict]:
    by_batter = defaultdict(list)
    for pitch in pitches:
        by_batter[(pitch["batter_id"], pitch["batter_name"])].append(pitch)
    players = []
    for (_, _), items in sorted(by_batter.items(), key=lambda item: item[0][1]):
        first = items[0]
        values = np.array([item["decision_value"] for item in items], dtype=float)
        opportunities = np.array([item["decision_opportunity"] for item in items], dtype=float)
        swings = [item for item in items if item["decision_type"] == "Swing"]
        takes = [item for item in items if item["decision_type"] == "Take"]
        in_zone = [item for item in items if item["in_zone"]]
        out_zone = [item for item in items if not item["in_zone"]]
        row = {
            "season": first["season"],
            "batter_id": first["batter_id"],
            "batter_name": first["batter_name"],
            "batter_stance": first.get("batter_stance"),
            "pitches_seen": len(items),
            "qualified_300": len(items) >= MIN_PITCHES,
            "swing_pct": round(100 * len(swings) / len(items), 6),
            "expected_swing_pct": round(100 * float(np.mean([
                item["expected_swing_probability"] for item in items
            ])), 6),
            "decision_value": round(float(values.sum()), 6),
            "decision_value_per_100": round(float(100 * values.mean()), 6),
            "decision_capture_pct": round(float(100 * values.sum() / opportunities.sum()), 6)
            if opportunities.sum() else 0.0,
            "swing_pitches": len(swings),
            "swing_decision_value_per_100": _per_100(swings),
            "take_pitches": len(takes),
            "take_decision_value_per_100": _per_100(takes),
            "in_zone_pitches": len(in_zone),
            "in_zone_decision_value_per_100": _per_100(in_zone),
            "out_zone_pitches": len(out_zone),
            "out_zone_decision_value_per_100": _per_100(out_zone),
        }
        for region in REGIONS:
            selected = [item for item in items if item["region"] == region]
            region_swings = [item for item in selected if item["decision_type"] == "Swing"]
            region_takes = [item for item in selected if item["decision_type"] == "Take"]
            prefix = region.lower()
            row[f"{prefix}_pitches"] = len(selected)
            row[f"{prefix}_decision_value_per_100"] = _per_100(selected)
            row[f"{prefix}_swing_decision_value_per_100"] = _per_100(region_swings)
            row[f"{prefix}_take_decision_value_per_100"] = _per_100(region_takes)
        players.append(row)
    _standardize(players, "decision_value_per_100", "zone_awareness_plus")
    _standardize(players, "in_zone_decision_value_per_100", "z_zone_awareness_plus")
    _standardize(players, "out_zone_decision_value_per_100", "o_zone_awareness_plus")
    return players


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]) if rows else [], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _team_lookup(web_root: Path, season: int) -> dict[str, str]:
    path = web_root / "data" / "leaderboards" / f"{season}.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    result = {}
    for dataset in data.get("datasets", []):
        for row in dataset.get("rows", []):
            name, team = str(row.get("Player") or "").strip(), str(row.get("Team") or "").strip()
            if name and team and name not in result:
                result[name] = team
    return result


def _mean(items: list[dict], field: str, scale: float = 1.0) -> float:
    return round(scale * float(np.mean([item[field] for item in items])), 4)


def _grid(items: list[dict]) -> list[dict]:
    cells = defaultdict(list)
    for item in items:
        x, z = float(item["x_relative"]), float(item["z_relative"])
        if abs(x) <= 2.5 and abs(z) <= 2.5:
            cells[(round(x / GRID_STEP), round(z / GRID_STEP))].append(item)
    result = []
    for (cx, cz), selected in sorted(cells.items()):
        swings = sum(item["decision_type"] == "Swing" for item in selected)
        cell = {
            "x": round(cx * GRID_STEP, 3),
            "z": round(cz * GRID_STEP, 3),
            "n": len(selected),
            "dv100": _mean(selected, "decision_value", 100),
            "delta": _mean(selected, "swing_minus_take_rv"),
            "swing_pct": round(100 * swings / len(selected), 3),
            "expected_swing_pct": _mean(selected, "expected_swing_probability", 100),
            "expected_swing_rv": _mean(selected, "expected_swing_rv"),
            "expected_take_rv": _mean(selected, "expected_take_rv"),
        }
        for field in PROBABILITY_FIELDS:
            cell[field] = _mean(selected, field, 100)
        result.append(cell)
    return result


def _write_web_data(
    web_root: Path, season: int, players: list[dict], pitches: list[dict], metadata: dict
) -> None:
    season_root = web_root / "data" / "zone_awareness" / str(season)
    season_root.mkdir(parents=True, exist_ok=True)
    teams = _team_lookup(web_root, season)
    for player in players:
        player["team"] = teams.get(player["batter_name"], "—")
    qualified = sorted(
        [player for player in players if player["qualified_300"]],
        key=lambda player: player["zone_awareness_plus"], reverse=True,
    )
    leaderboard = {
        "schema_version": 2,
        "season": season,
        "minimum_pitches": MIN_PITCHES,
        "qualified_batters": len(qualified),
        "players": players,
        "model": metadata["model"],
        "limitation": metadata["limitation"],
    }
    (season_root / "leaderboard.json").write_text(
        json.dumps(leaderboard, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    summaries = {player["batter_id"]: player for player in players}
    by_batter = defaultdict(list)
    for pitch in pitches:
        by_batter[pitch["batter_id"]].append(pitch)
    shards = defaultdict(dict)
    for batter_id, items in by_batter.items():
        shard = batter_id[0] if batter_id and batter_id[0].isdigit() else "other"
        shards[shard][batter_id] = {"summary": summaries[batter_id], "grid": _grid(items)}
    players_root = season_root / "players"
    players_root.mkdir(exist_ok=True)
    for path in players_root.glob("*.json"):
        path.unlink()
    for shard, payload in shards.items():
        (players_root / f"{shard}.json").write_text(
            json.dumps({"season": season, "players": payload}, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )

    catalog_path = web_root / "data" / "zone_awareness" / "index.json"
    catalog = {"schema_version": 2, "seasons": []}
    if catalog_path.exists():
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["seasons"] = sorted(set(catalog.get("seasons", [])) | {season}, reverse=True)
    catalog["default_season"] = max(catalog["seasons"])
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_zone_awareness_v2(
    root: Path,
    season: int = 2026,
    source: Path | None = None,
    web_root: Path | None = None,
) -> dict:
    source = source or root / "data" / "processed" / (
        "decision_pitches.parquet" if season == 2026 else f"decision_pitches_{season}.parquet"
    )
    rows, excluded = [], Counter()
    for row in pq.read_table(source).to_pylist():
        outcome = _outcome(row)
        if (
            int(row.get("season") or season) != season
            or row.get("decision_type") not in {"Swing", "Take"}
            or row.get("raw_run_value") is None
            or not row.get("batter_name")
            or outcome is None
        ):
            excluded["unsupported_or_missing"] += 1
            continue
        row["model_outcome"] = outcome
        rows.append(row)
    predictions, model = _fit_staged_models(rows)
    pitches = []
    for index, row in enumerate(rows):
        swing = float(predictions["expected_swing_rv"][index])
        take = float(predictions["expected_take_rv"][index])
        preference = swing - take
        swung = row["decision_type"] == "Swing"
        pitch = {
            "season": season,
            "batter_id": str(row.get("batter_id") or ""),
            "batter_name": str(row.get("batter_name") or ""),
            "batter_stance": row.get("batter_stance"),
            "x_relative": row.get("x_relative"),
            "z_relative": row.get("z_relative"),
            "region": _region(row),
            "in_zone": abs(float(row["x_relative"])) <= 1 and abs(float(row["z_relative"])) <= 1,
            "decision_type": row["decision_type"],
            "model_outcome": row["model_outcome"],
            "swing_minus_take_rv": round(preference, 8),
            "decision_value": round(preference if swung else -preference, 8),
            "decision_opportunity": round(abs(preference), 8),
        }
        for field, values in predictions.items():
            pitch[field] = round(float(values[index]), 8)
        pitches.append(pitch)
    players = _player_rows(pitches)

    processed = root / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(players), processed / f"zone_awareness_v2_batters_{season}.parquet")
    _write_csv(root / "exports" / f"kbo_zone_awareness_v2_{season}.csv", players)
    metadata = {
        "schema_version": 2,
        "season": season,
        "source": str(source.relative_to(root)),
        "pitches": len(pitches),
        "batters": len(players),
        "qualified_batters": sum(row["qualified_300"] for row in players),
        "minimum_pitches": MIN_PITCHES,
        "model": model,
        "excluded": dict(excluded),
        "limitation": "In-play value is estimated without exit velocity or launch angle; this is an observational counterfactual approximation.",
    }
    (processed / f"kbo_zone_awareness_v2_{season}.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_web_data(web_root or root / "web", season, players, pitches, metadata)
    return metadata


def build_zone_awareness_v2_series(
    root: Path, seasons: tuple[int, ...] = (2022, 2023, 2024, 2025, 2026)
) -> dict:
    from .swing_take import build_decision_pitches

    summaries, combined = [], []
    for season in sorted(set(seasons)):
        source = root / "data" / "processed" / (
            "decision_pitches.parquet" if season == 2026 else f"decision_pitches_{season}.parquet"
        )
        if not source.exists():
            workbook = root / "exports" / f"visualbaseball_savant_{season}_latest.xlsx"
            build_decision_pitches(root, season, workbook, source)
        summaries.append(build_zone_awareness_v2(root, season, source))
        combined.extend(pq.read_table(
            root / "data" / "processed" / f"zone_awareness_v2_batters_{season}.parquet"
        ).to_pylist())
    combined.sort(key=lambda row: (row["season"], row["batter_name"], row["batter_id"]))
    _write_csv(root / "exports" / "kbo_zone_awareness_v2_2022_2026.csv", combined)
    result = {
        "schema_version": 2,
        "seasons": [summary["season"] for summary in summaries],
        "season_summaries": summaries,
        "player_seasons": len(combined),
    }
    (root / "data" / "processed" / "kbo_zone_awareness_v2_2022_2026.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--seasons", nargs="+", type=int)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    result = (
        build_zone_awareness_v2_series(root, tuple(args.seasons))
        if args.seasons else build_zone_awareness_v2(root, args.season)
    )
    print(json.dumps(result, ensure_ascii=False))
