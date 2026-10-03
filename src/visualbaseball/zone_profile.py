"""Build compact, filterable pitcher zone profiles from canonical curated pitches."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path

from .curated import _number, load_rows
from .publish import write_json, write_shards


X_MIN = -2.0
X_MAX = 2.0
Z_MIN = 0.0
Z_MAX = 4.5
BUCKET_SIZE = 0.5
SAVANT_STRIKE_ZONE = {"left": -1.0, "right": 1.0, "bottom": 1.5, "top": 3.5}
HOME_PLATE_WIDTH_FT = 17 / 12


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _bucket(value: float, minimum: float, maximum: float) -> int | None:
    if not minimum <= value < maximum:
        return None
    return int((value - minimum) / BUCKET_SIZE)


def _pitch_type(row: dict) -> str:
    return str(row.get("pitch_type_kr") or row.get("pitch_type") or row.get("pitch_type_code") or "기타").strip()


def _pitcher_throws(row: dict) -> str:
    """Infer throwing side from release position used by the published feed."""
    release_x = _number(row.get("release_x_50"))
    if release_x is None or abs(release_x) < 0.1:
        return ""
    return "L" if release_x > 0 else "R"


def _batting_result(row: dict) -> tuple[int, int]:
    if not _truthy(row.get("is_pa_terminal")):
        return 0, 0
    result = str(row.get("pa_result") or "").strip()
    if not result or result in {"볼넷", "사구", "고의사"} or "SF" in result or result.endswith("희"):
        return 0, 0
    hit = result.endswith(("안", "이", "삼", "홈")) or "홈런" in result
    return 1, int(hit)


COLUMNS = {
    "batter": ["balls", "strikes", "pitcher_throws", "pitch_type", "x_bin", "z_bin", "total", "swings", "whiffs", "contacts", "in_play", "velo_sum", "velo_n", "zone", "pitches", "at_bats", "hits"],
    "pitcher": ["balls", "strikes", "pitch_type", "x_bin", "z_bin", "total", "swings", "whiffs", "contacts", "in_play", "velo_sum", "velo_n", "zone", "pitches", "at_bats", "hits"],
}
SCHEMA_VERSIONS = {"batter": 2, "pitcher": 1}


def _pitch_counts(row: dict, season: int) -> tuple[tuple, list] | None:
    """(shared group key parts, the 11 counters this pitch adds) or None when it is not eligible."""
    if row.get("season") != season or str(row.get("parse_status") or "") != "ok":
        return None
    px, pz = _number(row.get("px")), _number(row.get("pz"))
    if px is None or pz is None:
        return None
    x_bin = _bucket(px, X_MIN, X_MAX)
    z_bin = _bucket(pz, Z_MIN, Z_MAX)
    if x_bin is None or z_bin is None:
        return None
    balls = row.get("balls_before")
    strikes = row.get("strikes_before")
    if not isinstance(balls, int) or not isinstance(strikes, int):
        return None
    top, bottom = _number(row.get("sz_top")), _number(row.get("sz_bottom"))
    swing = _truthy(row.get("is_swing"))
    contact = _truthy(row.get("is_contact"))
    velocity = _number(row.get("velocity_kmh"))
    at_bat, hit = _batting_result(row)
    counts = [
        1, int(swing), int(swing and not contact), int(contact), int(_truthy(row.get("is_in_play"))),
        velocity if velocity is not None else 0, int(velocity is not None),
        int(abs(px) <= 10 / 12 and bottom is not None and top is not None and bottom <= pz <= top),
        1, at_bat, hit,
    ]
    return (balls, strikes, _pitch_type(row), x_bin, z_bin), counts


def _accumulate(rows: list[dict], season: int) -> tuple[dict[str, dict[str, dict]], int]:
    players_by_role: dict[str, dict[str, dict]] = {"batter": {}, "pitcher": {}}
    eligible = 0
    for row in rows:
        pitch = _pitch_counts(row, season)
        if pitch is None:
            continue
        (balls, strikes, pitch_type, x_bin, z_bin), counts = pitch
        for role in ("batter", "pitcher"):
            name = str(row.get(f"{role}_name") or "").strip()
            if not name:
                continue
            player_id = str(row.get(f"{role}_id") or name).strip()
            if player_id not in players_by_role[role]:
                players_by_role[role][player_id] = {"id": player_id, "name": name, "pitches": 0, "groups": defaultdict(lambda: [0] * 11)}
            player = players_by_role[role][player_id]
            player["pitches"] += 1
            group_key = (
                (balls, strikes, _pitcher_throws(row), pitch_type, x_bin, z_bin)
                if role == "batter"
                else (balls, strikes, pitch_type, x_bin, z_bin)
            )
            aggregate = player["groups"][group_key]
            for index, value in enumerate(counts):
                aggregate[index] += value
        eligible += 1
    return players_by_role, eligible


def _player_payload(season: int, role: str, player_id: str, player: dict, filename: str) -> dict:
    records = [
        [*key, *[round(value, 3) if isinstance(value, float) else value for value in values]]
        for key, values in player["groups"].items()
    ]
    return {
        "schema_version": SCHEMA_VERSIONS[role],
        "season": season,
        "role": role,
        "source": f"data/curated/pitches/season={season}",
        "player": {"id": player_id, "name": player["name"], "file": filename},
        "coordinates": {"x_min": X_MIN, "x_max": X_MAX, "z_min": Z_MIN, "z_max": Z_MAX, "bucket_size": BUCKET_SIZE},
        "strike_zone": SAVANT_STRIKE_ZONE,
        "home_plate": {"width_ft": round(HOME_PLATE_WIDTH_FT, 6), "gap_ft": 1 / 3},
        "columns": COLUMNS[role],
        "records": records,
    }


def _write_role(root: Path, season: int, role: str, players: dict[str, dict]) -> list[dict]:
    """Write one role's player shards and return its search-index entries."""
    role_index = []
    shards: dict[str, dict] = defaultdict(dict)
    for player_id, player in sorted(players.items(), key=lambda item: item[1]["name"]):
        shard = player_id[0] if player_id and player_id[0].isdigit() else "other"
        filename = f"{shard}.json"
        shards[shard][player_id] = _player_payload(season, role, player_id, player, filename)
        role_index.append({"id": player_id, "name": player["name"], "file": filename, "pitches": player["pitches"]})
    write_shards(root / "web" / "data" / "zones" / str(season) / role,
                 {shard: {"season": season, "role": role, "players": entries} for shard, entries in shards.items()})
    return role_index


def build_zone_profiles(root: Path, season: int) -> tuple[int, int]:
    """Export compact batter and pitcher JSON profiles plus a shared search index."""
    rows = load_rows(root, "pitches", season)
    if not rows:
        return 0, 0
    players_by_role, eligible = _accumulate(rows, season)
    index_players = {role: _write_role(root, season, role, players) for role, players in players_by_role.items()}

    legacy_output = root / "web" / "data" / "zones" / str(season)
    for legacy_file in legacy_output.glob("*.json"):
        legacy_file.unlink()

    index_path = root / "web" / "data" / "zones" / "index.json"
    catalog = {"seasons": [], "players": {}}
    if index_path.exists():
        catalog = json.loads(index_path.read_text(encoding="utf-8"))
    catalog.setdefault("players", {})[str(season)] = index_players
    catalog["seasons"] = sorted((int(value) for value in catalog["players"]), reverse=True)
    write_json(index_path, catalog, compact=False)
    return eligible, sum(len(players) for players in index_players.values())


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--season", type=int, required=True)
    args = parser.parse_args()
    rows, players = build_zone_profiles(Path(args.root).resolve(), args.season)
    print(f"exported {rows} pitches for {players} batter/pitcher profiles")
