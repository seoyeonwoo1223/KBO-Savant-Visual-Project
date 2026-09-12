"""Small, manifest-backed cache keys for production metric builds."""
from __future__ import annotations

import json
from pathlib import Path

from .curated import file_sha256, value_sha256


# Keep dependencies explicit: this file is the build graph, not another scanner.
SPECS = {
    "excel": (("games", "events", "pitches"), ("export_excel.py",), ()),
    "arm_angle": (("pitches",), ("arm_angle.py",), ("data/batter_handedness.json",)),
    "swing_take": (("pitches",), ("swing_take.py",), ()),
    "plate_discipline": (("pitches",), ("plate_discipline.py", "swing_take.py"), ()),
    "zone_decision": (("pitches", "events"), ("zone_decision.py", "swing_take.py", "pitch_arsenal.py"), ("data/batter_handedness.json", "data/curated/players/player_bio.parquet")),
    "plate_decision": (("pitches",), ("plate_decision_v1.py", "swing_take.py"), ()),
    "zone_profiles": (("pitches",), ("zone_profile.py",), ()),
    "pitch_arsenal": (("pitches",), ("pitch_arsenal.py",), ("data/batter_handedness.json", "data/park_adjustments/{season}_VB_Park_Adjustment_v1.0.xlsx")),
    "blocking": (("games", "pitches"), ("blocking.py",), ()),
}


def _index(root: Path) -> dict:
    path = root / "data" / "curated" / "partition-index.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"seasons": {}}


def metric_input_hash(root: Path, season: int, name: str) -> str:
    tables, modules, files = SPECS[name]
    index = _index(root)
    games = index.get("seasons", {}).get(str(season), {}).get("games", {})
    if name == "arm_angle":
        games = {f"{year}/{game_id}": item for year, value in index.get("seasons", {}).items()
                 for game_id, item in value.get("games", {}).items()}
    if not games:  # Pre-migration datasets retain per-game provenance manifests.
        directory = root / "data" / "curated" / "sources" / f"season={season}"
        games = {path.stem: {"tables": {table: json.loads(path.read_text(encoding="utf-8")).get("pitch_sha256") for table in tables}}
                 for path in sorted(directory.glob("*.json"))}
    # The index records table hashes per game, so this never discovers Parquet shards.
    source = {game_id: {table: item.get("tables", {}).get(table) for table in tables}
              for game_id, item in sorted(games.items())}
    package = root / "src" / "visualbaseball"
    if not package.exists():  # Temporary build roots in tests still use the installed source.
        package = Path(__file__).parent
    code = {module: file_sha256(package / module) for module in modules}
    extras = {}
    for template in files:
        path = root / template.format(season=season)
        extras[template] = file_sha256(path) if path.exists() else None
    return value_sha256({"metric": name, "season": season, "source": source, "code": code, "extras": extras})


def _path(root: Path, season: int, name: str) -> Path:
    return root / "data" / "metrics" / "_state" / str(season) / f"{name}.json"


def needs_build(root: Path, season: int, name: str) -> bool:
    path, digest = _path(root, season, name), metric_input_hash(root, season, name)
    if not path.exists():
        return True
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("input_sha256") != digest
    except (OSError, json.JSONDecodeError):
        return True


def mark_built(root: Path, season: int, name: str) -> None:
    path = _path(root, season, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"metric": name, "season": season,
                                "input_sha256": metric_input_hash(root, season, name)}, indent=2) + "\n", encoding="utf-8")
