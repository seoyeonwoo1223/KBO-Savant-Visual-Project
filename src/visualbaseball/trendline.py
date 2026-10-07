"""Publish game-level counts for player trends and matching league baselines."""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import json
import math

from .curated import _number, load_rows
from .pitch_types import PITCH_NAMES, pitch_code
from .publish import write_json, write_shards
from .teams import TEAM_CODES


TRENDLINE_SEASONS = tuple(range(2019, 2027))
TREND_TEAM_CODES = {**TEAM_CODES, "SK": "SK"}
# Store numerators and denominators, never pre-averaged percentages.
FIELDS = ("pitches", "velocity_sum", "velocity_n", "swing_n", "swings", "contact_n", "contacts",
          "location_n", "in_zone", "z_n", "z_swings", "o_n", "o_swings", "swstr_n", "whiffs", "pa", "k", "bb", "pa_unknown")
INDEX = {key: i for i, key in enumerate(FIELDS)}
PITCH_COLORS = {"FF": "#d62f4b", "FT": "#b9415e", "SI": "#f09a22", "FC": "#8d6d61", "SL": "#b5b516",
                "ST": "#3aa8a6", "CH": "#4bb783", "CU": "#76c8c5", "FS": "#7556b8"}
COLUMNS = ["pitch_id", "game_id", "game_date", "inning_half", "event_seq", "batter_id", "batter_name",
           "pitcher_id", "pitcher_name", "pitch_type_code", "pitch_type_kr", "velocity_kmh", "is_swing",
           "is_contact", "px", "pz", "sz_bottom", "sz_top", "is_pa_terminal", "pa_id", "pa_type", "pa_result"]


def pitch_counts(row, terminal=False):
    counts = [0] * len(FIELDS)
    counts[INDEX["pitches"]] = 1
    velocity = _number(row.get("velocity_kmh"))
    if velocity is not None and math.isfinite(velocity) and velocity > 0:
        counts[INDEX["velocity_sum"]], counts[INDEX["velocity_n"]] = velocity, 1
    swing, contact = row.get("is_swing"), row.get("is_contact")
    if swing is not None:
        counts[INDEX["swing_n"]], counts[INDEX["swings"]] = 1, int(bool(swing))
        if not swing or contact is not None:
            counts[INDEX["swstr_n"]] = 1
    if swing and contact is not None:
        counts[INDEX["contact_n"]], counts[INDEX["contacts"]] = 1, int(bool(contact))
        counts[INDEX["whiffs"]] = int(not contact)
    _location_counts(counts, row, swing)
    result, kind = str(row.get("pa_result") or "").strip(), row.get("pa_type")
    if terminal and (result or kind in {"k", "hit", "hr"}):
        counts[INDEX["pa"]] = 1
        counts[INDEX["k"]] = int(kind == "k" or result == "삼진")
        # VB's bb type also includes hit-by-pitch; legacy seasons lack pa_type.
        counts[INDEX["bb"]] = int(result in {"볼넷", "고의사"})
    elif terminal:
        counts[INDEX["pa_unknown"]] = 1
    return counts


def _location_counts(counts, row, swing):
    values = [_number(row.get(key)) for key in ("px", "pz", "sz_bottom", "sz_top")]
    if any(value is None or not math.isfinite(value) for value in values):
        return
    px, pz, low, high = values
    if low >= high:
        return
    inside = abs(px) <= 10 / 12 and low <= pz <= high
    counts[INDEX["location_n"]], counts[INDEX["in_zone"]] = 1, int(inside)
    if swing is not None:
        prefix = "z" if inside else "o"
        counts[INDEX[f"{prefix}_n"]], counts[INDEX[f"{prefix}_swings"]] = 1, int(bool(swing))


def _add(target, counts):
    for i, value in enumerate(counts):
        target[i] += value


def _bucket():
    return {"all": [0] * len(FIELDS), "types": defaultdict(lambda: [0] * len(FIELDS))}


def _pack(bucket):
    counts = list(bucket["all"])
    counts[INDEX["velocity_sum"]] = round(counts[INDEX["velocity_sum"]], 6)
    types = {}
    for code, values in sorted(bucket["types"].items()):
        types[code] = list(values)
        types[code][INDEX["velocity_sum"]] = round(values[INDEX["velocity_sum"]], 6)
    return {"counts": counts, "types": types}


def aggregate(rows, games):
    final = {game["game_id"]: game for game in games if game.get("is_final") and game.get("away_team") in TREND_TEAM_CODES and game.get("home_team") in TREND_TEAM_CODES}
    players = {"pitcher": {}, "batter": {}}
    league = defaultdict(_bucket)
    terminal_seen = set()
    for row in sorted(rows, key=lambda r: (r["game_id"], int(r.get("event_seq") or 0))):
        game = final.get(row["game_id"])
        if not game or not row.get("game_date") or row.get("inning_half") not in {"top", "bottom"}:
            continue
        pa_key = row["game_id"], row.get("pa_id")
        terminal = bool(row.get("is_pa_terminal")) and bool(row.get("pa_id")) and pa_key not in terminal_seen
        if terminal:
            terminal_seen.add(pa_key)
        counts, code = pitch_counts(row, terminal), pitch_code(row)
        date = row["game_date"]
        _add(league[date]["all"], counts)
        _add(league[date]["types"][code or "UN"], counts)
        for role in players:
            _player_counts(players[role], row, role, game, counts, code)
    return players, league


def _player_counts(players, row, role, game, counts, code):
    player_id = str(row.get(f"{role}_id") or "").strip()
    name = str(row.get(f"{role}_name") or "").strip()
    if not player_id or not name:
        return
    entry = players.setdefault(player_id, {"id": player_id, "name": name, "games": {}})
    entry["name"] = name
    key = row["game_id"]
    if key not in entry["games"]:
        batting_side = "away" if row["inning_half"] == "top" else "home"
        side = batting_side if role == "batter" else ("home" if batting_side == "away" else "away")
        entry["games"][key] = {"game_id": key, "date": row["game_date"], "team": TREND_TEAM_CODES[game[f"{side}_team"]], "bucket": _bucket()}
    bucket = entry["games"][key]["bucket"]
    _add(bucket["all"], counts)
    _add(bucket["types"][code or "UN"], counts)


def _publish_players(directory, role, entries, season):
    shards, catalog = {}, []
    for player_id, player in sorted(entries.items()):
        records = [{key: value for key, value in game.items() if key != "bucket"} | _pack(game["bucket"])
                   for game in sorted(player["games"].values(), key=lambda g: (g["date"], g["game_id"]))]
        # ID shards keep an individual download small and retain pitchers with few outings.
        file = f"{player_id}.json"
        shards[player_id] = {"schema_version": 1, "season": season, "role": role, "id": player_id, "name": player["name"], "games": records}
        teams = list(dict.fromkeys(game["team"] for game in records))
        catalog.append({"id": player_id, "name": player["name"], "teams": teams, "games": len(records), "file": file})
    write_shards(directory / role / "players", shards)
    return catalog


def build_trendline(root, season=2026):
    if season not in TRENDLINE_SEASONS:
        raise ValueError("Trendline은 저장된 2019–2026 시즌을 지원합니다.")
    games = load_rows(root, "games", season, columns=["game_id", "is_final", "away_team", "home_team"])
    rows = load_rows(root, "pitches", season, columns=COLUMNS)
    players, league = aggregate(rows, games)
    output = root / "web/data/trendline" / str(season)
    output.mkdir(parents=True, exist_ok=True)
    catalog = {role: _publish_players(output, role, entries, season) for role, entries in players.items()}
    dates = sorted(league)
    write_json(output / "league.json", {"schema_version": 1, "season": season,
                                       "days": [{"date": date, **_pack(league[date])} for date in dates]})
    write_json(output / "index.json", {"schema_version": 1, "season": season, "as_of": dates[-1] if dates else None,
                                       "players": catalog, "games": len({g["game_id"] for entry in players["batter"].values() for g in entry["games"].values()})})
    summary = root / "data/curated/summary.json"
    available = json.loads(summary.read_text(encoding="utf-8")).get("seasons", {}) if summary.exists() else {str(season): {}}
    seasons = sorted((year for year in TRENDLINE_SEASONS if str(year) in available), reverse=True)
    write_json(output.parent / "index.json", {"schema_version": 1, "seasons": seasons, "fields": FIELDS,
                                             "pitch_names": {**PITCH_NAMES, "UN": "미분류"}, "pitch_colors": {**PITCH_COLORS, "UN": "#8c939c"}})
    return output / "index.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--season", type=int, default=2026)
    args = parser.parse_args()
    print(build_trendline(args.root, args.season))


if __name__ == "__main__":
    main()
