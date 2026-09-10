"""Prepare canonical 55 ft Arm Angle inputs; final angle calibration is out of scope."""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from statistics import median
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq

from .curated import file_sha256, load_rows, value_sha256


BIO_SCHEMA = pa.schema([
    ("player_id", pa.string()), ("player_name", pa.string()), ("birth_date", pa.string()),
    ("height_cm", pa.float64()), ("weight_kg", pa.float64()), ("throws", pa.string()),
    ("bats", pa.string()), ("team", pa.string()), ("position", pa.string()),
    ("source_name", pa.string()), ("source_url", pa.string()), ("source_sha256", pa.string()),
    ("source_updated_at", pa.string()),
])


def _atomic_table(path: Path, table: pa.Table) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{uuid4().hex}.tmp")
    pq.write_table(table, temporary, compression="zstd")
    temporary.replace(path)


def build_player_bio(root: Path, seasons: tuple[int, ...]) -> Path:
    handedness_path = root / "data" / "batter_handedness.json"
    handedness = json.loads(handedness_path.read_text(encoding="utf-8")) if handedness_path.exists() else {"seasons": {}}
    names, release_x, bats = {}, defaultdict(list), {}
    for season in seasons:
        for row in load_rows(root, "pitches", season, columns=["pitcher_id", "pitcher_name", "batter_id", "batter_name", "release_x_55"]):
            pitcher_id, batter_id = str(row.get("pitcher_id") or ""), str(row.get("batter_id") or "")
            if pitcher_id:
                names[pitcher_id] = str(row.get("pitcher_name") or names.get(pitcher_id, ""))
                if row.get("release_x_55") is not None:
                    release_x[pitcher_id].append(float(row["release_x_55"]))
            if batter_id:
                names[batter_id] = str(row.get("batter_name") or names.get(batter_id, ""))
        for player_id, value in handedness.get("seasons", {}).get(str(season), {}).get("players", {}).items():
            bats[str(player_id)] = str(value.get("bats") or "")
    manifests = []
    for season in seasons:
        for path in sorted((root / "data" / "curated" / "sources" / f"season={season}").glob("*.json")):
            manifests.append(json.loads(path.read_text(encoding="utf-8")))
    source_digest = value_sha256({
        "pitch_sha256": [item.get("pitch_sha256") for item in manifests],
        "handedness_sha256": file_sha256(handedness_path) if handedness_path.exists() else None,
    })
    updated_at = max((str(item.get("last_checked_at") or "") for item in manifests), default="") or None
    rows = [{
        "player_id": player_id, "player_name": name, "birth_date": None, "height_cm": None,
        "weight_kg": None, "throws": ("R" if median(release_x[player_id]) < 0 else "L") if release_x[player_id] else None,
        "bats": bats.get(player_id) or None, "team": None, "position": None,
        "source_name": "Visual Baseball PBP + canonical trajectory inference",
        "source_url": None, "source_sha256": source_digest, "source_updated_at": updated_at,
    } for player_id, name in sorted(names.items())]
    output = root / "data" / "curated" / "players" / "player_bio.parquet"
    _atomic_table(output, pa.Table.from_pylist(rows, schema=BIO_SCHEMA))
    return output


def build_arm_angle_input(root: Path, season: int, rebuild_bio: bool = True) -> Path:
    bio_path = root / "data" / "curated" / "players" / "player_bio.parquet"
    if rebuild_bio or not bio_path.exists():
        available = tuple(sorted(int(path.name.split("=", 1)[1]) for path in (root / "data/curated/pitches").glob("season=*") if path.name.split("=", 1)[1].isdigit()))
        bio_path = build_player_bio(root, available or (season,))
    bio = {row["player_id"]: row for row in pq.read_table(bio_path).to_pylist()}
    columns = [
        "season", "game_id", "pitch_id", "pitcher_id", "pitcher_name", "pitch_type_code",
        "release_x_55", "release_z_55", "vx_55", "vy_55", "vz_55", "trajectory_status",
    ]
    rows = []
    for pitch in load_rows(root, "pitches", season, columns=columns):
        player = bio.get(str(pitch["pitcher_id"]), {})
        rows.append({**pitch, "throws": player.get("throws"), "height_cm": player.get("height_cm"),
                     "weight_kg": player.get("weight_kg")})
    output = root / "data" / "metrics" / "arm_angle" / str(season) / "input.parquet"
    _atomic_table(output, pa.Table.from_pylist(rows))
    return output
