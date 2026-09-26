"""Fail unless every ABS season's ZA/SBJ output comes from the current code and agrees,
and every Pitch Plot season carries the current profile schema and build state.

daily_update runs this before anything is published (Release upload, data commit, and
through that the Pages deploy), so a partial rebuild can never go out mixed with older
seasons.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from visualbaseball.metric_state import _path, metric_input_hash
from visualbaseball.pitch_arsenal import PITCH_ARSENAL_SEASONS, PROFILE_SCHEMA_VERSION
from visualbaseball.zone_decision import MODEL_VERSION

SEASONS = (2024, 2025, 2026)


def _shard(batter_id: str) -> str:
    return batter_id[:2] if batter_id[:1].isdigit() else "other"


def problems(root: Path, seasons=SEASONS, model_version: str = MODEL_VERSION) -> list[str]:
    found = []
    index = json.loads((root / "web/data/zone_awareness/index.json").read_text(encoding="utf-8"))
    for season in seasons:
        base = root / "web/data/zone_awareness" / str(season)
        if season not in index.get("seasons", []):
            found.append(f"{season}: missing from index.json")
        try:
            board = json.loads((base / "leaderboard.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            found.append(f"{season}: unreadable leaderboard.json ({error})")
            continue
        if board.get("model_version") != model_version:
            found.append(f"{season}: model_version {board.get('model_version')} != {model_version}")
        players = {p["batter_id"]: p for p in board.get("players", [])}
        shards = {}
        for batter_id, player in players.items():
            name = _shard(batter_id)
            if name not in shards:
                try:
                    shards[name] = json.loads((base / "players" / f"{name}.json").read_text(encoding="utf-8"))["players"]
                except (OSError, json.JSONDecodeError, KeyError):
                    shards[name] = {}
            if shards[name].get(batter_id, {}).get("summary") != player:
                found.append(f"{season}: player file for {batter_id} missing or differs from leaderboard")
        try:
            with (root / "exports" / f"zone_decision_players_{season}.csv").open(encoding="utf-8-sig", newline="") as handle:
                rows = {row["batter_id"]: row for row in csv.DictReader(handle)}
        except OSError as error:
            found.append(f"{season}: unreadable CSV ({error})")
            rows = None
        if rows is not None:
            if set(rows) != set(players):
                found.append(f"{season}: CSV batters differ from leaderboard")
            else:
                for batter_id, row in rows.items():
                    expected = players[batter_id]["za_raw"]
                    value = float(row["za_raw"]) if row["za_raw"] else None
                    if (value is None) != (expected is None) or (value is not None and abs(value - expected) > 1e-9):
                        found.append(f"{season}: CSV za_raw for {batter_id} differs from leaderboard")
        try:
            stored = json.loads(_path(root, season, "zone_decision").read_text(encoding="utf-8")).get("input_sha256")
        except (OSError, json.JSONDecodeError):
            stored = None
        if stored != metric_input_hash(root, season, "zone_decision"):
            found.append(f"{season}: build state missing or stale")
    return found


def pitch_arsenal_problems(root: Path, seasons=PITCH_ARSENAL_SEASONS, schema_version: int = PROFILE_SCHEMA_VERSION) -> list[str]:
    found = []
    for season in seasons:
        base = root / "web/data/pitch_arsenal" / str(season)
        try:
            players = json.loads((base / "index.json").read_text(encoding="utf-8"))["players"]
        except (OSError, json.JSONDecodeError, KeyError) as error:
            found.append(f"pitch arsenal {season}: unreadable index.json ({error})")
            continue
        shards = {}
        for player in players:
            if player["file"] not in shards:
                try:
                    shards[player["file"]] = json.loads((base / player["file"]).read_text(encoding="utf-8"))["players"]
                except (OSError, json.JSONDecodeError, KeyError):
                    shards[player["file"]] = {}
            profile = shards[player["file"]].get(player["id"])
            if profile is None or profile.get("schema_version") != schema_version:
                found.append(f"pitch arsenal {season}: profile {player['id']} missing or not schema {schema_version}")
                break
        try:
            stored = json.loads(_path(root, season, "pitch_arsenal").read_text(encoding="utf-8")).get("input_sha256")
        except (OSError, json.JSONDecodeError):
            stored = None
        if stored != metric_input_hash(root, season, "pitch_arsenal"):
            found.append(f"pitch arsenal {season}: build state missing or stale")
    return found


def main() -> None:
    found = problems(Path(".")) + pitch_arsenal_problems(Path("."))
    for line in found:
        print(f"Output check failed: {line}")
    if found:
        sys.exit(1)
    print(f"ZA outputs agree for {', '.join(map(str, SEASONS))} ({MODEL_VERSION}); "
          f"Pitch Plot schema {PROFILE_SCHEMA_VERSION} for {', '.join(map(str, PITCH_ARSENAL_SEASONS))}")


if __name__ == "__main__":
    main()
