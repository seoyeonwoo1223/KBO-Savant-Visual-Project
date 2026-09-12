"""Canonical raw -> compact Parquet boundary used by every metric."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Iterable
from uuid import uuid4

import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq


SCHEMA_VERSION = 1
PARSER_REVISION = 1
CM_PER_FOOT = 30.48
PLATE_Y_FT = 17 / 12
TRAJECTORY_FIELDS = ("x0", "y0", "z0", "vx0", "vy0", "vz0", "ax", "ay", "az")

PITCH_INTEGER_FIELDS = {
    "season", "event_seq", "pitch_number", "game_pitch_number", "inning", "runs_on_pitch", "pa_rbi",
    "balls_before", "balls_after", "strikes_before", "strikes_after", "outs_before", "outs_after",
    "away_score_before", "away_score_after", "home_score_before", "home_score_after",
    "base_state_code_before", "base_state_code_after", "re24_state_code_before", "re24_state_code_after",
    "re288_state_code_before", "re288_state_code_after",
}
PITCH_BOOLEAN_FIELDS = {
    "is_swing", "is_take", "is_contact", "is_in_play", "is_pa_terminal", "is_wild_pitch",
    "is_passed_ball", "trajectory_valid",
}
PITCH_FLOAT_FIELDS = {
    "velocity_kmh", "velocity_mph", "px", "pz", "sz_top", "sz_bottom", "release_height_cm",
    "arrival_time_s", "vertical_movement_cm", "horizontal_movement_cm", "drop_angle",
    *TRAJECTORY_FIELDS,
    "source_y0", "release_x_50", "release_z_50", "release_x_55", "release_z_55",
    "vx_50", "vy_50", "vz_50", "vx_55", "vy_55", "vz_55",
    "plate_x_error_cm", "plate_z_error_cm", "relh_minus_z50_cm",
}
PITCH_STRING_FIELDS = {
    "game_date", "game_id", "stadium", "pa_id", "pitch_id", "inning_half", "batter_id", "batter_position",
    "batter_name", "batter_team", "batter_stance", "pitcher_id", "pitcher_name", "catcher_id",
    "catcher_name", "catcher_source", "pitch_type", "pitch_type_code", "pitch_type_kr",
    "pitch_call_code", "pitch_result", "pa_result", "pa_type", "description", "naver_pitch_id",
    "naver_match_status", "parse_status", "fetched_at", "source_url", "runner_1b_id_before",
    "runner_1b_id_after", "runner_2b_id_before", "runner_2b_id_after", "runner_3b_id_before",
    "runner_3b_id_after", "base_state_before", "base_state_after", "trajectory_status",
}

EVENT_INTEGER_FIELDS = {
    "event_seq", "inning", "outs_before", "outs_after", "runs_on_event", "away_score_before",
    "away_score_after", "home_score_before", "home_score_after",
}
EVENT_STRING_FIELDS = {
    "game_id", "stadium", "inning_half", "pa_id", "event_type", "event_code", "description",
    "batter_id", "batter_name", "pitcher_id", "pitcher_name", "base_state_before", "base_state_after",
    "parse_status",
}
GAME_INTEGER_FIELDS = {"season", "away_score", "home_score"}
GAME_BOOLEAN_FIELDS = {"is_final"}
GAME_STRING_FIELDS = {
    "game_date", "game_id", "away_team", "home_team", "away_starter_name", "home_starter_name", "stadium", "game_status", "fetched_at",
    "source_url", "source_hash", "validation_status",
}


def _schema(strings: set[str], integers: set[str], floats: set[str] = frozenset(),
            booleans: set[str] = frozenset()) -> pa.Schema:
    types = ({name: pa.string() for name in strings}
             | {name: pa.int64() for name in integers}
             | {name: pa.float64() for name in floats}
             | {name: pa.bool_() for name in booleans})
    return pa.schema((name, types[name]) for name in sorted(types))


PITCH_SCHEMA = _schema(PITCH_STRING_FIELDS, PITCH_INTEGER_FIELDS, PITCH_FLOAT_FIELDS, PITCH_BOOLEAN_FIELDS)
EVENT_SCHEMA = _schema(EVENT_STRING_FIELDS, EVENT_INTEGER_FIELDS)
GAME_SCHEMA = _schema(GAME_STRING_FIELDS, GAME_INTEGER_FIELDS, booleans=GAME_BOOLEAN_FIELDS)
SCHEMAS = {"pitches": PITCH_SCHEMA, "events": EVENT_SCHEMA, "games": GAME_SCHEMA}

COORDINATE_METADATA = {
    "source_y0": "feet from the plate origin; copied from raw pitch.y0",
    "release_x_50": "centimetres at y=50 ft, catcher-view x convention",
    "release_z_50": "centimetres at y=50 ft",
    "release_x_55": "centimetres at y=55 ft, catcher-view x convention",
    "release_z_55": "centimetres at y=55 ft",
    "vx_50/vy_50/vz_50": "feet per second at y=50 ft",
    "vx_55/vy_55/vz_55": "feet per second at y=55 ft",
    "release_height_cm": "raw provider relH; not recomputed",
    "missing": "null means absent/uncomputable; false remains an observed boolean",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def value_sha256(value: object) -> str:
    return sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def schema_sha256() -> str:
    return value_sha256({
        "version": SCHEMA_VERSION,
        "parser_revision": PARSER_REVISION,
        "parser_sha256": file_sha256(Path(__file__).with_name("parser.py")),
        "schemas": {name: str(schema) for name, schema in SCHEMAS.items()},
        "coordinates": COORDINATE_METADATA,
    })


def _number(value) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _time_to_plane(row: dict, target_y: float) -> float | None:
    y0, vy, ay = (_number(row.get(name)) for name in ("y0", "vy0", "ay"))
    if None in (y0, vy, ay):
        return None
    if abs(ay) < 1e-12:
        return (target_y - y0) / vy if abs(vy) > 1e-12 else None
    discriminant = vy * vy - 2 * ay * (y0 - target_y)
    if discriminant < 0:
        return None
    roots = ((-vy + math.sqrt(discriminant)) / ay, (-vy - math.sqrt(discriminant)) / ay)
    return min(roots, key=abs)


def _at_plane(row: dict, target_y: float) -> tuple[float, float, float, float, float] | None:
    time = _time_to_plane(row, target_y)
    values = [_number(row.get(name)) for name in ("x0", "z0", "vx0", "vy0", "vz0", "ax", "ay", "az")]
    if time is None or any(value is None for value in values) or abs(time) > 1:
        return None
    x, z, vx, vy, vz, ax, ay, az = values
    return (
        (x + vx * time + .5 * ax * time * time) * CM_PER_FOOT,
        (z + vz * time + .5 * az * time * time) * CM_PER_FOOT,
        vx + ax * time, vy + ay * time, vz + az * time,
    )


def normalize_trajectory(source: dict) -> dict:
    """Preserve a pitch and add deterministic 50/55 ft trajectory values."""
    row = dict(source)
    row["source_y0"] = _number(row.get("y0"))
    missing = [name for name in TRAJECTORY_FIELDS if _number(row.get(name)) is None]
    at_50 = _at_plane(row, 50)
    at_55 = _at_plane(row, 55)
    if missing:
        status = "missing:" + ",".join(missing)
    elif at_50 is None or at_55 is None:
        status = "no_solution"
    elif row["source_y0"] not in {50.0, 55.0}:
        status = "unexpected_y0"
    else:
        status = "valid"
    row["trajectory_status"] = status
    row["trajectory_valid"] = status == "valid"
    for prefix, values in (("50", at_50), ("55", at_55)):
        names = (f"release_x_{prefix}", f"release_z_{prefix}", f"vx_{prefix}", f"vy_{prefix}", f"vz_{prefix}")
        row.update(dict(zip(names, values or (None,) * 5)))
    arrival = _number(row.get("arrival_time_s"))
    x0, z0, vx0, vz0, ax, az = (_number(row.get(name)) for name in ("x0", "z0", "vx0", "vz0", "ax", "az"))
    px, pz = _number(row.get("px")), _number(row.get("pz"))
    if arrival is not None and None not in (x0, z0, vx0, vz0, ax, az, px, pz):
        row["plate_x_error_cm"] = (x0 + vx0 * arrival + .5 * ax * arrival ** 2 - px) * CM_PER_FOOT
        row["plate_z_error_cm"] = (z0 + vz0 * arrival + .5 * az * arrival ** 2 - pz) * CM_PER_FOOT
    else:
        row["plate_x_error_cm"] = row["plate_z_error_cm"] = None
    relh = _number(row.get("release_height_cm"))
    row["relh_minus_z50_cm"] = relh - row["release_z_50"] if relh is not None and row["release_z_50"] is not None else None
    return row


def _clean_rows(rows: Iterable[dict], schema: pa.Schema) -> list[dict]:
    cleaned = []
    for source in rows:
        row = {}
        for field in schema:
            value = source.get(field.name)
            if value is None:
                row[field.name] = None
            elif pa.types.is_string(field.type):
                row[field.name] = str(value)
            elif pa.types.is_boolean(field.type):
                row[field.name] = bool(value)
            elif pa.types.is_integer(field.type):
                number = _number(value); row[field.name] = int(number) if number is not None else None
            else:
                row[field.name] = _number(value)
        cleaned.append(row)
    return cleaned


def _stable_rows(rows: Iterable[dict]) -> list[dict]:
    return [{key: value for key, value in sorted(row.items()) if key not in {"fetched_at", "source_url", "source_hash"}}
            for row in rows]


def pitch_sha256(game: dict, events: list[dict], pitches: list[dict]) -> str:
    return value_sha256({"game": _stable_rows([game])[0], "events": _stable_rows(events), "pitches": _stable_rows(pitches)})


def raw_pitch_count(payload: dict | None) -> int | None:
    if payload is None:
        return None
    return sum(len(pa.get("pitches") or []) for half in payload.get("pbpData", []) for pa in half.get("pas") or [])


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _atomic_parquet(path: Path, rows: list[dict], schema: pa.Schema) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{uuid4().hex}.tmp")
    table = pa.Table.from_pylist(_clean_rows(rows, schema), schema=schema)
    pq.write_table(table.replace_schema_metadata({
        b"schema_version": str(SCHEMA_VERSION).encode(),
        b"schema_sha256": schema_sha256().encode(),
        b"coordinate_metadata": canonical_bytes(COORDINATE_METADATA),
    }), temporary, compression="zstd")
    temporary.replace(path)


def curated_path(root: Path, kind: str, season: int, game_id: str) -> Path:
    return root / "data" / "curated" / kind / f"season={season}" / f"{game_id}.parquet"


def partition_index_path(root: Path) -> Path:
    return root / "data" / "curated" / "partition-index.json"


def _partition_index(root: Path) -> dict:
    path = partition_index_path(root)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"schema_version": 1, "layout": "game", "seasons": {}}


def _write_partition_index(root: Path, index: dict) -> None:
    _atomic_json(partition_index_path(root), index)


def _month(game: dict) -> str:
    value = str(game.get("game_date") or game.get("game_id") or "")
    return value[5:7] if len(value) >= 7 and value[4] == "-" else value[4:6]


def _monthly_path(root: Path, kind: str, season: int, month: str) -> Path:
    return root / "data" / "curated" / kind / f"season={season}" / f"month={month}.parquet"


def _replace_monthly_game(root: Path, kind: str, season: int, month: str, game_id: str,
                          rows: list[dict], schema: pa.Schema) -> None:
    path = _monthly_path(root, kind, season, month)
    old = pq.ParquetFile(path).read().to_pylist() if path.exists() else []
    _atomic_parquet(path, [row for row in old if str(row.get("game_id")) != game_id] + rows, schema)


def _monthly_game_exists(root: Path, season: int, month: str, game_id: str) -> bool:
    for kind in SCHEMAS:
        path = _monthly_path(root, kind, season, month)
        if not path.is_file(): return False
        if kind != "events" and game_id not in set(pq.ParquetFile(path).read(columns=["game_id"]).column("game_id").to_pylist()): return False
    return True


def source_manifest_path(root: Path, season: int, game_id: str) -> Path:
    return root / "data" / "curated" / "sources" / f"season={season}" / f"{game_id}.json"


def write_game(root: Path, game: dict, events: list[dict], pitches: list[dict], *,
               raw_payload: dict | None = None, provenance: dict | None = None,
               force: bool = False) -> dict:
    """Atomically replace only one game's shards; identical analysis input is a no-op."""
    season, game_id = int(game["season"]), str(game["game_id"])
    normalized = [normalize_trajectory(row) for row in pitches]
    digest, schema_digest = pitch_sha256(game, events, normalized), schema_sha256()
    manifest_path = source_manifest_path(root, season, game_id)
    previous = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    index = _partition_index(root)
    compact = index.get("layout") == "month"
    prior = index.get("seasons", {}).get(str(season), {}).get("games", {}).get(game_id, {})
    if compact and prior and not _monthly_game_exists(root, season, str(prior.get("month") or _month(game)), game_id):
        raise FileNotFoundError(f"compact partition is missing or corrupt for {game_id}; rebuild the month from retained raw data")
    shards_exist = (_monthly_game_exists(root, season, str(prior.get("month") or _month(game)), game_id) if compact and prior
                    else all(curated_path(root, kind, season, game_id).is_file() for kind in SCHEMAS))
    changed = force or not shards_exist or previous.get("pitch_sha256") != digest or previous.get("schema_sha256") != schema_digest
    if changed:
        if compact:
            month = _month(game)
            old_month = str(prior.get("month") or month)
            if old_month != month:
                for kind, schema in SCHEMAS.items():
                    _replace_monthly_game(root, kind, season, old_month, game_id, [], schema)
            _replace_monthly_game(root, "games", season, month, game_id, [game], GAME_SCHEMA)
            _replace_monthly_game(root, "events", season, month, game_id, events, EVENT_SCHEMA)
            _replace_monthly_game(root, "pitches", season, month, game_id, normalized, PITCH_SCHEMA)
        else:
            _atomic_parquet(curated_path(root, "games", season, game_id), [game], GAME_SCHEMA)
            _atomic_parquet(curated_path(root, "events", season, game_id), events, EVENT_SCHEMA)
            _atomic_parquet(curated_path(root, "pitches", season, game_id), normalized, PITCH_SCHEMA)
    now = utc_now()
    raw_digest = value_sha256(raw_payload) if raw_payload is not None else None
    excluded = max(0, (raw_pitch_count(raw_payload) or len(normalized)) - len(normalized))
    exclusion_reasons = {}
    if excluded:
        reason = "SOURCE_POST_THIRD_OUT" if any(event.get("event_code") == "SOURCE_POST_THIRD_OUT" for event in events) else "PARSER_NOT_REPRESENTED"
        exclusion_reasons[reason] = excluded
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "game_id": game_id,
        "season": season,
        "first_collected_at": previous.get("first_collected_at") or now,
        "last_collected_at": now if changed else previous.get("last_collected_at", now),
        "last_checked_at": now,
        "raw_sha256": raw_digest if raw_digest is not None else previous.get("raw_sha256"),
        "pitch_sha256": digest,
        "schema_sha256": schema_digest,
        "revision": int(previous.get("revision", 0)) + int(changed),
        "observed_y0": sorted({row["source_y0"] for row in normalized if row["source_y0"] is not None}),
        "raw_pitch_count": raw_pitch_count(raw_payload),
        "curated_pitch_count": len(normalized),
        "parse_excluded": excluded,
        "parse_exclusion_reasons": exclusion_reasons,
        "provenance": provenance or previous.get("provenance") or {"type": "visualbaseball_json"},
    }
    _atomic_json(manifest_path, manifest)
    games = index.setdefault("seasons", {}).setdefault(str(season), {}).setdefault("games", {})
    games[game_id] = {"game_date": game.get("game_date"), "month": _month(game), "revision": manifest["revision"],
                      "tables": {"games": value_sha256(_stable_rows([game])), "events": value_sha256(_stable_rows(events)),
                                 "pitches": value_sha256(_stable_rows(normalized))}}
    _write_partition_index(root, index)
    return {"changed": changed, "manifest": manifest, "pitches": normalized}


def _field_changes(before: object, after: object, prefix: str = "", limit: int = 200) -> list[str]:
    changes: list[str] = []
    def walk(left, right, path):
        if len(changes) >= limit or left == right:
            return
        if isinstance(left, dict) and isinstance(right, dict):
            for key in sorted(set(left) | set(right)):
                walk(left.get(key), right.get(key), f"{path}.{key}" if path else str(key))
        elif isinstance(left, list) and isinstance(right, list):
            for index in range(max(len(left), len(right))):
                walk(left[index] if index < len(left) else None, right[index] if index < len(right) else None, f"{path}[{index}]")
        else:
            changes.append(path)
    walk(before, after, prefix)
    return changes


def audit_raw_replacement(root: Path, season: int, game_id: str, before: dict, after: dict) -> dict | None:
    old_hash, new_hash = value_sha256(before), value_sha256(after)
    if old_hash == new_hash:
        return None
    record = {
        "observed_at": utc_now(), "game_id": game_id, "previous_raw_sha256": old_hash,
        "current_raw_sha256": new_hash, "previous_pitch_count": raw_pitch_count(before),
        "current_pitch_count": raw_pitch_count(after), "changed_fields": _field_changes(before, after),
    }
    path = root / "data" / "curated" / "audit" / f"season={season}" / f"{game_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        output.flush()
    return record


def load_table(root: Path, kind: str, season: int, columns: Iterable[str] | None = None,
               *, game_id: str | None = None, player_id: str | None = None,
               player_role: str = "pitcher") -> pa.Table:
    """Read selected shard columns; season/game/player pruning happens in Arrow."""
    directory = root / "data" / "curated" / kind / f"season={season}"
    index = _partition_index(root)
    entry = index.get("seasons", {}).get(str(season), {}).get("games", {}).get(str(game_id)) if game_id else None
    files = ([_monthly_path(root, kind, season, str(entry["month"]))] if entry and index.get("layout") == "month"
             else [directory / f"{game_id}.parquet"] if game_id else sorted(directory.glob("*.parquet")))
    files = [path for path in files if path.is_file()]
    selected = list(columns) if columns is not None else None
    if not files:
        schema = SCHEMAS[kind]
        if selected is not None:
            schema = pa.schema(schema.field(name) for name in selected)
        return pa.Table.from_pylist([], schema=schema)
    dataset = ds.dataset([str(path) for path in files], format="parquet")
    expression = ds.field("season") == season if "season" in dataset.schema.names else None
    if game_id:
        clause = ds.field("game_id") == str(game_id)
        expression = clause if expression is None else expression & clause
    if player_id:
        field = f"{player_role}_id"
        clause = ds.field(field) == str(player_id)
        expression = clause if expression is None else expression & clause
    return dataset.to_table(columns=selected, filter=expression)


def load_rows(*args, **kwargs) -> list[dict]:
    return load_table(*args, **kwargs).to_pylist()


def validation_summary(root: Path, season: int) -> dict:
    table = load_table(root, "pitches", season, columns=[
        "pitch_id", "game_id", "source_y0", "trajectory_status", "plate_x_error_cm",
        "plate_z_error_cm", "relh_minus_z50_cm",
    ])
    rows = table.to_pylist()
    def distribution(name: str) -> dict:
        values = sorted(abs(float(row[name])) for row in rows if row.get(name) is not None)
        def quantile(probability: float):
            if not values: return None
            return values[round((len(values) - 1) * probability)]
        return {"n": len(values), "median_abs_cm": quantile(.5), "p95_abs_cm": quantile(.95)}
    ids = [row["pitch_id"] for row in rows]
    manifests = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((root / "data/curated/sources" / f"season={season}").glob("*.json"))]
    raw_count = sum(item.get("raw_pitch_count") or item["curated_pitch_count"] for item in manifests)
    excluded = sum(item.get("parse_excluded", 0) for item in manifests)
    exclusion_reasons = defaultdict(int)
    for item in manifests:
        for reason, count in item.get("parse_exclusion_reasons", {}).items():
            exclusion_reasons[reason] += count
    return {
        "schema_version": SCHEMA_VERSION, "schema_sha256": schema_sha256(), "season": season,
        "games": len({row["game_id"] for row in rows}), "raw_pitches": raw_count,
        "curated_pitches": len(rows), "parse_excluded": excluded,
        "parse_exclusion_reasons": dict(sorted(exclusion_reasons.items())),
        "pitch_id_duplicates": len(ids) - len(set(ids)),
        "trajectory_status": dict(sorted(__import__("collections").Counter(row["trajectory_status"] for row in rows).items())),
        "source_y0": dict(sorted(__import__("collections").Counter(str(row["source_y0"]) for row in rows).items())),
        "plate_x_error": distribution("plate_x_error_cm"),
        "plate_z_error": distribution("plate_z_error_cm"),
        "relh_minus_z50": distribution("relh_minus_z50_cm"),
    }


def write_schema(root: Path) -> Path:
    path = root / "data" / "curated" / "schema.json"
    if path.exists():
        try:
            if json.loads(path.read_text(encoding="utf-8")).get("schema_sha256") == schema_sha256():
                return path
        except (json.JSONDecodeError, OSError):
            pass
    _atomic_json(path, {
        "schema_version": SCHEMA_VERSION, "schema_sha256": schema_sha256(),
        "pitch_identity": "provider-stable game_id + plate-appearance sequence + pitch_number; existing pitch_id is retained",
        "tables": {name: [{"name": field.name, "type": str(field.type), "nullable": field.nullable} for field in schema]
                   for name, schema in SCHEMAS.items()},
        "coordinates": COORDINATE_METADATA,
    })
    return path
