"""Manifest-backed, fail-closed production metric build state."""
from __future__ import annotations
import json
from pathlib import Path
from .curated import file_sha256, schema_sha256, source_sha256, value_sha256

# Each metric records its transitive builder/helper dependency set.
SPECS = {
 "leaderboards": (("games", "pitches"), ("data/leaderboards/source/constants.xlsx", "data/leaderboards/source/{season}_running.json"), ("web/data/leaderboards/{season}.json", "web/data/leaderboards/index.json")),
 "excel": (("games", "events", "pitches"), (), ("exports/visualbaseball_savant_{season}_latest.xlsx",)),
 "arm_angle": (("pitches",), ("data/batter_handedness.json",), ("data/metrics/arm_angle/{season}/input.parquet",)),
 "swing_take": (("pitches",), (), ("web/data/swing_take/{season}/index.json",)),
 "plate_discipline": (("pitches",), (), ("data/metrics/plate_discipline/{season}/plate_discipline_pitches.parquet",)),
 "zone_decision": (("pitches", "events"), ("data/batter_handedness.json", "data/curated/players/player_bio.parquet", "data/park_adjustments/{season}_VB_Park_Adjustment_v1.0.xlsx"), ("data/metrics/zone_awareness/{season}/report.json", "web/data/zone_awareness/{season}/leaderboard.json", "web/data/zone_awareness/{season}/teams.json", "web/data/zone_awareness/index.json")),
 "zone_profiles": (("pitches",), (), ("web/data/zones/index.json",)),
 "pitch_arsenal": (("pitches",), ("data/batter_handedness.json", "data/curated/players/player_bio.parquet", "data/tracking/player_heights.csv", "data/models/estimated_arm_angle_v1.json", "data/models/estimated_arm_angle_v2.json", "data/models/estimated_arm_angle_v3.json"), ("web/data/pitch_arsenal/{season}/index.json",)),
 "blocking": (("games", "pitches"), (), ("data/metrics/blocking/{season}/pitches.parquet", "web/data/blocking/{season}/leaderboard.json")),
 "movement_zones": (("pitches",), ("data/curated/players/player_bio.parquet", "data/tracking/player_id_crosswalk.json", *(f"data/tracking/raw/season={year}/trackman_history.csv" for year in range(2019, 2025))), ("web/data/movement_zones/profiles.json",)),
}
CODE = {
 "leaderboards": ("leaderboard_vb.py", "publish.py", "curated.py"),
 "excel": ("export_excel.py", "curated.py"), "arm_angle": ("arm_angle.py", "curated.py"),
 "swing_take": ("swing_take.py", "publish.py", "curated.py"), "plate_discipline": ("plate_discipline.py", "swing_take.py", "publish.py", "curated.py"),
 "zone_decision": ("zone_decision.py", "plate_decision_v1.py", "teams.py", "pitch_types.py", "batter_stance.py", "movement_calibration.py", "swing_take.py", "publish.py", "curated.py"),
 "zone_profiles": ("zone_profile.py", "publish.py", "curated.py"),
 "pitch_arsenal": ("pitch_arsenal.py", "pitch_types.py", "batter_stance.py", "movement_calibration.py", "estimated_arm_angle.py", "estimated_arm_angle_numeric.py", "numeric_arm_angle_features.py", "arm_angle_aggregation.py", "arm_angle_reference.py", "eaa_movement_calibration.py", "publish.py", "curated.py"),
 "blocking": ("blocking.py", "publish.py", "curated.py"),
 "movement_zones": ("movement_zones.py", "movement_calibration.py", "pitch_types.py", "batter_stance.py", "curated.py", "../../analysis/movement_calibration/match_trackman.py", "../../scripts/build_trackman_id_crosswalk.py"),
}

def _index(root: Path) -> dict:
 path = root / "data" / "curated" / "partition-index.json"
 return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"seasons": {}}

def metric_input_hash(root: Path, season: int, name: str) -> str:
 tables, extras, _ = SPECS[name]; index = _index(root)
 games = index.get("seasons", {}).get(str(season), {}).get("games", {})
 if name in {"arm_angle", "movement_zones"}: games = {f"{year}/{game}": value for year, data in index.get("seasons", {}).items() for game, value in data.get("games", {}).items()}
 if not games:
  directory = root / "data" / "curated" / "sources" / f"season={season}"
  games = {p.stem: {"tables": {table: json.loads(p.read_text(encoding="utf-8")).get("pitch_sha256") for table in tables}} for p in sorted(directory.glob("*.json"))}
 source = {game: {table: value.get("tables", {}).get(table) for table in tables} for game, value in sorted(games.items())}
 package = root / "src" / "visualbaseball"
 if not package.exists(): package = Path(__file__).parent
 code = {name: source_sha256(package / name) for name in CODE[name]}
 files = {item: (file_sha256(path) if (path := root / item.format(season=season)).exists() else None) for item in extras}
 return value_sha256({"metric": name, "season": season, "source": source, "schema_sha256": schema_sha256(), "code": code, "extras": files})

def _path(root: Path, season: int, name: str) -> Path: return root / "data" / "metrics" / "_state" / str(season) / f"{name}.json"

def needs_build(root: Path, season: int, name: str) -> bool:
 _, _, outputs = SPECS[name]
 if any(not (root / output.format(season=season)).is_file() for output in outputs): return True
 if name == "swing_take" and not (root / "data/metrics/swing_take" / str(season) / ("decision_pitches.parquet" if season == 2026 else f"decision_pitches_{season}.parquet")).is_file(): return True
 if name in {"swing_take", "pitch_arsenal", "zone_profiles", "zone_decision"} and not _web_shards_exist(root, season, name): return True
 try: return json.loads(_path(root, season, name).read_text(encoding="utf-8")).get("input_sha256") != metric_input_hash(root, season, name)
 except (OSError, json.JSONDecodeError): return True

def _shard(player_id: str, digits: int) -> str: return player_id[:digits] if player_id[0].isdigit() else "other"

def _expected_shards(root: Path, season: int, name: str):
 """Every player shard the metric's published index points at."""
 if name == "zone_profiles":
  data = json.loads((root / "web/data/zones/index.json").read_text(encoding="utf-8")); base = root / "web/data/zones" / str(season)
  yield from (base / role / player["file"] for role, players in data["players"][str(season)].items() for player in players)
  yield from (base / "league" / f"{role}.json" for role in data["players"][str(season)])
  return
 base = root / "web/data" / ("zone_awareness" if name == "zone_decision" else name) / str(season)
 players = json.loads((base / ("leaderboard.json" if name == "zone_decision" else "index.json")).read_text(encoding="utf-8")).get("players", [])
 for player in players:
  if name == "swing_take": yield base / "players" / f"{_shard(str(player['id']), 1)}.json"
  elif name == "zone_decision": yield base / "players" / f"{_shard(str(player.get('batter_id') or player.get('id')), 2)}.json"
  else: yield base / player["file"]

def _web_shards_exist(root: Path, season: int, name: str) -> bool:
 try: return all(path.is_file() for path in _expected_shards(root, season, name))
 except (KeyError, OSError, json.JSONDecodeError): return False

def mark_built(root: Path, season: int, name: str) -> None:
 path = _path(root, season, name); path.parent.mkdir(parents=True, exist_ok=True)
 path.write_text(json.dumps({"metric": name, "season": season, "input_sha256": metric_input_hash(root, season, name)}, indent=2) + "\n", encoding="utf-8")
