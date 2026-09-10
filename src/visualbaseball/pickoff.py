"""Team pickoff attempts per 100 runner-pitches.

Numerator: Naver relay pickoff events (independent non-pitch events).
Denominator: Visual Baseball curated pitches thrown while any base is occupied.
"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha1
import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from .curated import load_rows
from .naver import NaverEnrichment, NAVER_SCHEMA_VERSION


PICKOFF_SCHEMA = pa.schema([
    ("season", pa.int64()),
    ("game_id", pa.string()),
    ("inning", pa.int64()),
    ("inning_half", pa.string()),
    ("source_seq", pa.string()),
    ("pickoff_event_id", pa.string()),
    ("offense_team", pa.string()),
    ("defense_team", pa.string()),
    ("pitcher_id", pa.string()),
    ("batter_id", pa.string()),
    ("runner_name", pa.string()),
    ("pickoff_base", pa.int64()),
    ("pitch_number_context", pa.int64()),
    ("is_pickoff_out", pa.bool_()),
    ("is_pickoff_error", pa.bool_()),
    ("description", pa.string()),
])

SUMMARY_SCHEMA = pa.schema([
    ("season", pa.int64()),
    ("team", pa.string()),
    ("pickoff_throws", pa.int64()),
    ("pickoffs_received", pa.int64()),
    ("defensive_runner_pitches", pa.int64()),
    ("offensive_runner_pitches", pa.int64()),
    ("pickoff_rate_per_100_runner_pitches", pa.float64()),
    ("received_pickoff_rate_per_100_runner_pitches", pa.float64()),
])


def _write_parquet(path: Path, rows: list[dict[str, Any]], schema: pa.Schema) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), temporary, compression="zstd")
    temporary.replace(path)


def _teams_for_half(game: dict[str, Any], inning_half: str) -> tuple[str, str]:
    if inning_half == "top":
        return str(game.get("away_team") or ""), str(game.get("home_team") or "")
    return str(game.get("home_team") or ""), str(game.get("away_team") or "")


def _runner_on(row: dict[str, Any]) -> bool:
    return any(bool(row.get(field)) for field in (
        "runner_1b_id_before", "runner_2b_id_before", "runner_3b_id_before"
    )) or int(row.get("base_state_code_before") or 0) != 0


def build_pickoff(root: Path, season: int = 2026, storage_root: Path | None = None) -> Path:
    """Build normalized pickoff events and team rates from retained sources."""
    storage_root = storage_root or root
    games = load_rows(root, "games", season)
    pitches = load_rows(root, "pitches", season)
    game_lookup = {str(game.get("game_id")): game for game in games}

    events: list[dict[str, Any]] = []
    naver_dir = storage_root / "data" / "raw" / "naver" / str(season)
    for path in sorted(naver_dir.glob("*.json")):
        try:
            enrichment = NaverEnrichment.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if enrichment.schema_version < NAVER_SCHEMA_VERSION or enrichment.coverage != "relay":
            continue
        game = game_lookup.get(enrichment.game_id)
        if not game:
            continue
        for source in enrichment.pickoff_events:
            inning_half = str(source.get("inning_half") or "")
            offense, defense = _teams_for_half(game, inning_half)
            identity = "|".join([
                enrichment.game_id,
                str(source.get("inning") or 0),
                inning_half,
                str(source.get("source_seq") or ""),
                str(source.get("text") or ""),
            ])
            events.append({
                "season": season,
                "game_id": enrichment.game_id,
                "inning": int(source.get("inning") or 0),
                "inning_half": inning_half,
                "source_seq": str(source.get("source_seq") or ""),
                "pickoff_event_id": sha1(identity.encode("utf-8")).hexdigest()[:20],
                "offense_team": offense,
                "defense_team": defense,
                "pitcher_id": str(source.get("pitcher_id") or ""),
                "batter_id": str(source.get("batter_id") or ""),
                "runner_name": str(source.get("runner_name") or ""),
                "pickoff_base": int(source["pickoff_base"]) if source.get("pickoff_base") else None,
                "pitch_number_context": int(source.get("pitch_number_context") or 0),
                "is_pickoff_out": bool(source.get("is_pickoff_out")),
                "is_pickoff_error": bool(source.get("is_pickoff_error")),
                "description": str(source.get("text") or ""),
            })

    # Defensive and offensive denominators count the same runner-on pitch once,
    # attributed to the fielding and batting team respectively.
    defensive_runner_pitches: dict[str, int] = defaultdict(int)
    offensive_runner_pitches: dict[str, int] = defaultdict(int)
    for pitch in pitches:
        if not _runner_on(pitch):
            continue
        game = game_lookup.get(str(pitch.get("game_id") or ""), {})
        offense, defense = _teams_for_half(game, str(pitch.get("inning_half") or ""))
        if offense:
            offensive_runner_pitches[offense] += 1
        if defense:
            defensive_runner_pitches[defense] += 1

    thrown: dict[str, int] = defaultdict(int)
    received: dict[str, int] = defaultdict(int)
    for event in events:
        if event["defense_team"]:
            thrown[event["defense_team"]] += 1
        if event["offense_team"]:
            received[event["offense_team"]] += 1

    teams = sorted({str(game.get(field) or "") for game in games for field in ("away_team", "home_team")} - {""})
    summary = []
    for team in teams:
        defensive = defensive_runner_pitches[team]
        offensive = offensive_runner_pitches[team]
        summary.append({
            "season": season,
            "team": team,
            "pickoff_throws": thrown[team],
            "pickoffs_received": received[team],
            "defensive_runner_pitches": defensive,
            "offensive_runner_pitches": offensive,
            "pickoff_rate_per_100_runner_pitches": round(thrown[team] / defensive * 100, 3) if defensive else None,
            "received_pickoff_rate_per_100_runner_pitches": round(received[team] / offensive * 100, 3) if offensive else None,
        })
    summary.sort(key=lambda row: (-(row["pickoff_rate_per_100_runner_pitches"] or -1), row["team"]))

    curated = root / "data" / "curated" / "pickoffs" / f"season={season}" / "events.parquet"
    metrics = root / "data" / "metrics" / "pickoff" / str(season)
    _write_parquet(curated, events, PICKOFF_SCHEMA)
    _write_parquet(metrics / "team_summary.parquet", summary, SUMMARY_SCHEMA)

    web_output = root / "web" / "data" / "pickoff" / str(season)
    web_output.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "season": season,
        "metric": "Pickoff attempts per 100 runner-pitches",
        "definition": {
            "pickoff_throws": "Naver relay events containing 견제, attributed to the defensive team",
            "pickoffs_received": "Same events attributed to the offensive team",
            "runner_pitch": "A regular pitch with at least one runner on 1B, 2B or 3B before the pitch",
            "pickoff_rate_per_100_runner_pitches": "pickoff_throws / defensive_runner_pitches * 100",
            "received_pickoff_rate_per_100_runner_pitches": "pickoffs_received / offensive_runner_pitches * 100",
        },
        "coverage": {
            "games_with_curated_pitch_data": len(games),
            "games_with_pickoff_relay_cache": len({row["game_id"] for row in events}),
            "pickoff_events": len(events),
        },
        "teams": summary,
    }
    (web_output / "team_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return web_output / "team_summary.json"
