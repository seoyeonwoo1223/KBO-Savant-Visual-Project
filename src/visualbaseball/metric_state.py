"""Manifest-backed, fail-closed production metric build state."""
from __future__ import annotations
import json
from pathlib import Path
from .curated import file_sha256, schema_sha256, value_sha256

# A package-wide code fingerprint is deliberately conservative: helper edits
# cannot leave a production metric stale through an incomplete hand-written DAG.
SPECS = {
 "excel": (("games", "events", "pitches"), (), ("exports/visualbaseball_savant_{season}_latest.xlsx",)),
 "arm_angle": (("pitches",), ("data/batter_handedness.json",), ("data/metrics/arm_angle/{season}/input.parquet",)),
 "swing_take": (("pitches",), (), ("data/metrics/swing_take/{season}/decision_pitches.parquet", "web/data/swing_take/{season}/index.json")),
 "plate_discipline": (("pitches",), (), ("data/metrics/plate_discipline/{season}/plate_discipline_pitches.parquet",)),
 "zone_decision": (("pitches", "events"), ("data/batter_handedness.json", "data/curated/players/player_bio.parquet", "data/park_adjustments/{season}_VB_Park_Adjustment_v1.0.xlsx"), ("data/metrics/zone_awareness/{season}/report.json", "web/data/zone_awareness/{season}/leaderboard.json")),
 "plate_decision": (("pitches",), ("data/park_adjustments/{season}_VB_Park_Adjustment_v1.0.xlsx",), ("data/metrics/plate_decision/{season}/plate_decision_v1_report_{season}.json",)),
 "zone_profiles": (("pitches",), (), ("web/data/zones/index.json",)),
 "pitch_arsenal": (("pitches",), ("data/batter_handedness.json", "data/park_adjustments/{season}_VB_Park_Adjustment_v1.0.xlsx"), ("web/data/pitch_arsenal/{season}/index.json",)),
 "blocking": (("games", "pitches"), (), ("data/metrics/blocking/{season}/pitches.parquet", "web/data/blocking/{season}/leaderboard.json")),
}

def _index(root: Path) -> dict:
 path = root / "data" / "curated" / "partition-index.json"
 return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"seasons": {}}

def metric_input_hash(root: Path, season: int, name: str) -> str:
 tables, extras, _ = SPECS[name]; index = _index(root)
 games = index.get("seasons", {}).get(str(season), {}).get("games", {})
 if name == "arm_angle": games = {f"{year}/{game}": value for year, data in index.get("seasons", {}).items() for game, value in data.get("games", {}).items()}
 if not games:
  directory = root / "data" / "curated" / "sources" / f"season={season}"
  games = {p.stem: {"tables": {table: json.loads(p.read_text(encoding="utf-8")).get("pitch_sha256") for table in tables}} for p in sorted(directory.glob("*.json"))}
 source = {game: {table: value.get("tables", {}).get(table) for table in tables} for game, value in sorted(games.items())}
 package = root / "src" / "visualbaseball"
 if not package.exists(): package = Path(__file__).parent
 code = {p.name: file_sha256(p) for p in sorted(package.glob("*.py"))}
 files = {item: (file_sha256(path) if (path := root / item.format(season=season)).exists() else None) for item in extras}
 return value_sha256({"metric": name, "season": season, "source": source, "schema_sha256": schema_sha256(), "code": code, "extras": files})

def _path(root: Path, season: int, name: str) -> Path: return root / "data" / "metrics" / "_state" / str(season) / f"{name}.json"

def needs_build(root: Path, season: int, name: str) -> bool:
 _, _, outputs = SPECS[name]
 if any(not (root / output.format(season=season)).is_file() for output in outputs): return True
 try: return json.loads(_path(root, season, name).read_text(encoding="utf-8")).get("input_sha256") != metric_input_hash(root, season, name)
 except (OSError, json.JSONDecodeError): return True

def mark_built(root: Path, season: int, name: str) -> None:
 path = _path(root, season, name); path.parent.mkdir(parents=True, exist_ok=True)
 path.write_text(json.dumps({"metric": name, "season": season, "input_sha256": metric_input_hash(root, season, name)}, indent=2) + "\n", encoding="utf-8")
