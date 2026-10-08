"""Canonical 투구를 날짜별 정적 검색 파일로 내보냅니다."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .curated import _number, load_rows
from .pitch_types import PITCH_NAMES, pitch_code
from .publish import add_catalog_season, write_json, write_shards
from .strikeouts import third_strike

FINDER_SEASONS = tuple(range(2022, 2027))
PITCH_COLUMNS = [
    "game_id", "pa_id", "pitcher_id", "pitcher_name", "batter_id", "batter_name",
    "inning", "inning_half", "event_seq", "pitch_number", "game_pitch_number",
    "pitch_id", "pitch_type_code", "pitch_type_kr", "pitch_type", "velocity_kmh",
    "balls_before", "strikes_before", "pitch_call_code", "is_take", "is_swing",
    "is_pa_terminal", "pa_result", "outs_before", "base_state_before",
    "away_score_before", "home_score_before", "parse_status",
]
PA_COLUMNS = ["id", "game", "inning", "half", "half_pa", "result", "outcome"]
ROW_COLUMNS = [
    "pa", "pitcher", "batter", "number", "game_number", "type", "velocity",
    "balls", "strikes", "call", "action", "terminal", "outs", "bases",
    "away_score", "home_score", "status",
]


def outcome(result: str | None, strikeout: bool = False) -> str:
    """위치 접두사가 붙는 VB 결과를 분류합니다. 미확인을 아웃으로 대체하지 않습니다.

    strikeout은 2스트라이크 S·T 판정으로 끝난 타석입니다. 결과가 비었거나 WP·포실(낫아웃)이어도 삼진입니다.
    """
    if strikeout:
        return "strikeout"
    result = str(result or "").strip()
    exact = {"삼진": "strikeout", "낫아웃": "strikeout", "볼넷": "walk",
             "고의사": "intentional_walk", "고의4구": "intentional_walk", "사구": "hbp"}
    if result in exact:
        return exact[result]
    suffixes = [("홈", "home_run"), ("홈런", "home_run"), ("안", "single"),
                ("이", "double"), ("삼", "triple"), ("야선", "fielders_choice"),
                ("실", "error"), ("SF", "sacrifice"), ("희", "sacrifice"),
                ("병", "out"), ("땅", "out"), ("비", "out"), ("파", "out"), ("라", "out")]
    return next((name for suffix, name in suffixes if result.endswith(suffix)), "unknown")


def _pa_order(events: list[dict], pitches: list[dict]) -> dict[tuple[str, str], int]:
    # 0구 고의사·대타 등이 있는 타석도 이닝 내 타석 순서에 포함합니다.
    first = {}
    for row in [*events, *pitches]:
        if row.get("pa_id"):
            key = (row["game_id"], row["pa_id"])
            if key not in first or (row.get("event_seq") or 0) < (first[key].get("event_seq") or 0):
                first[key] = row
    counts, orders = defaultdict(int), {}
    for key, row in sorted(first.items(), key=lambda item: (item[0][0], item[1].get("event_seq") or 0, item[0][1])):
        half = (row["game_id"], row.get("inning"), row.get("inning_half"))
        counts[half] += 1
        orders[key] = counts[half]
    return orders


def _pitch_type(row: dict) -> str:
    return pitch_code(row) or str(row.get("pitch_type_kr") or row.get("pitch_type") or "미확인").strip()


def _row(row: dict, pa_index: int) -> list:
    return [pa_index, row.get("pitcher_id"), row.get("batter_id"),
            row.get("pitch_number"), row.get("game_pitch_number"), _pitch_type(row),
            _number(row.get("velocity_kmh")), row.get("balls_before"), row.get("strikes_before"),
            row.get("pitch_call_code"), "take" if row.get("is_take") else "swing" if row.get("is_swing") else "unknown",
            row.get("is_pa_terminal"), row.get("outs_before"), row.get("base_state_before"),
            row.get("away_score_before"), row.get("home_score_before"), row.get("parse_status")]


def _player_index(pitches: list[dict], games: dict[str, dict]) -> dict:
    players = {"pitcher": {}, "batter": {}}
    for row in pitches:
        game = games[row["game_id"]]
        for role in players:
            player_id = row.get(f"{role}_id")
            if not player_id:
                continue
            player = players[role].setdefault(player_id, {
                "id": player_id, "name": row.get(f"{role}_name") or player_id,
                "pitches": 0, "files": set(), "teams": set(),
            })
            player["pitches"] += 1
            player["files"].add(game["game_date"].replace("-", "") + ".json")
            half = row.get("inning_half")
            if half in {"top", "bottom"}:
                home = (half == "top") if role == "pitcher" else (half == "bottom")
                team = game.get("home_team" if home else "away_team")
                if team:
                    player["teams"].add(team)
    return {role: [{**player, "files": sorted(player["files"]), "teams": sorted(player["teams"])}
                   for player in sorted(entries.values(), key=lambda player: (player["name"], player["id"]))]
            for role, entries in players.items()}


def _outcome(row: dict) -> str:
    terminal = bool(row.get("is_pa_terminal"))
    return outcome(row.get("pa_result"), terminal and third_strike(row.get("strikes_before"), row.get("pitch_call_code")))


def _date_payload(rows: list[dict], games: dict[str, dict], orders: dict) -> dict:
    pas, pa_indices, records = [], {}, []
    for row in rows:
        key = (row["game_id"], row["pa_id"])
        if key not in pa_indices:
            pa_indices[key] = len(pas)
            pas.append([row["pa_id"], row["game_id"], row.get("inning"), row.get("inning_half"),
                        orders[key], row.get("pa_result"), _outcome(row)])
        elif row.get("is_pa_terminal"):
            pas[pa_indices[key]][5:] = [row.get("pa_result"), _outcome(row)]
        records.append(_row(row, pa_indices[key]))
    return {"schema_version": 1, "pa_columns": PA_COLUMNS, "columns": ROW_COLUMNS,
            "games": {game_id: games[game_id] for game_id in sorted({row["game_id"] for row in rows})},
            "pas": pas, "rows": records}


def build_conditional_finder(root: Path, season: int = 2026) -> dict:
    if season not in FINDER_SEASONS:
        raise ValueError("Conditional Finder는 2022–2026 시즌을 지원합니다.")
    games = {row["game_id"]: row for row in load_rows(root, "games", season, columns=[
        "game_id", "game_date", "away_team", "home_team", "stadium",
    ])}
    pitches = load_rows(root, "pitches", season, columns=PITCH_COLUMNS)
    events = load_rows(root, "events", season, columns=["game_id", "pa_id", "inning", "inning_half", "event_seq"])
    if not pitches:
        raise ValueError(f"season={season}: 검색 가능한 투구가 없습니다.")
    pitches.sort(key=lambda row: (row["game_id"], row.get("event_seq") or 0, row.get("game_pitch_number") or 0))
    orders = _pa_order(events, pitches)
    by_date = defaultdict(list)
    for row in pitches:
        by_date[games[row["game_id"]]["game_date"]].append(row)
    base = root / "web" / "data" / "conditional_finder"
    target = base / str(season)
    target.mkdir(parents=True, exist_ok=True)
    shards = {day.replace("-", ""): _date_payload(rows, games, orders) for day, rows in sorted(by_date.items())}
    write_shards(target / "dates", shards)
    index = {
        "schema_version": 1, "season": season, "source": "canonical curated games/events/pitches",
        "pitches": len(pitches), "games": len({row["game_id"] for row in pitches}),
        "date_range": [min(by_date), max(by_date)], "players": _player_index(pitches, games),
        "pitch_types": [{"id": name, "name": PITCH_NAMES.get(name, name)}
                        for name in sorted({_pitch_type(row) for row in pitches})],
        "stadiums": sorted({game["stadium"] for game in games.values() if game.get("stadium")}),
        "teams": sorted({game[key] for game in games.values() for key in ("away_team", "home_team") if game.get(key)}),
        "coverage": {"missing_velocity": sum(_number(row.get("velocity_kmh")) is None for row in pitches),
                     "missing_pitch_type": sum(_pitch_type(row) == "미확인" for row in pitches)},
        "files": [{"file": day.replace("-", "") + ".json", "date": day, "pitches": len(rows)}
                  for day, rows in sorted(by_date.items())],
    }
    write_json(target / "index.json", index)
    add_catalog_season(base / "index.json", season)
    return index
