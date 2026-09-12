"""Small, readable inventory of the curated and published data.

`partition-index.json` is the integrity record and grows with every game, so it is
the wrong thing to open just to learn what a season contains. This writes one small
file answering that question from Parquet footers alone, so tools and agents can
orient without enumerating thousands of files or loading a row.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pyarrow.parquet as pq

from .curated import SCHEMAS, _atomic_json, schema_sha256, utc_now
from .metric_state import SPECS, needs_build

SUMMARY_PATH = ("data", "curated", "summary.json")


def _season_dirs(root: Path, kind: str) -> dict[int, Path]:
    base = root / "data" / "curated" / kind
    seasons = {}
    for directory in sorted(base.glob("season=*")) if base.is_dir() else []:
        try:
            seasons[int(directory.name.split("=", 1)[1])] = directory
        except ValueError:
            continue
    return seasons


def _table_stats(directory: Path) -> dict:
    rows = files = size = 0
    for path in sorted(directory.glob("*.parquet")):
        files += 1
        size += path.stat().st_size
        rows += pq.ParquetFile(path).metadata.num_rows
    return {"rows": rows, "files": files, "bytes": size}


def _counts(directory: Path, pattern: str = "*") -> int:
    return sum(1 for path in directory.glob(pattern) if path.is_file()) if directory.is_dir() else 0


def build_summary(root: Path) -> Path:
    root = Path(root).resolve()
    index_path = root / "data" / "curated" / "partition-index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    layout = index.get("layout", "game")
    seasons: dict[str, dict] = {}
    for kind in SCHEMAS:
        for season, directory in _season_dirs(root, kind).items():
            entry = seasons.setdefault(str(season), {"tables": {}})
            entry["tables"][kind] = _table_stats(directory)
    for season, entry in seasons.items():
        games = index.get("seasons", {}).get(season, {}).get("games", {})
        dates = sorted(value.get("game_date") for value in games.values() if value.get("game_date"))
        entry["games"] = len(games) or _counts(root / "data" / "curated" / "sources" / f"season={season}", "*.json")
        entry["months"] = sorted({str(value.get("month")) for value in games.values()}) if games else []
        entry["date_range"] = [dates[0], dates[-1]] if dates else None
        entry["metrics"] = sorted(
            path.parent.name for path in (root / "data" / "metrics").glob(f"*/{season}")
            if path.is_dir() and not path.parent.name.startswith("_"))
        # What a production run would rebuild right now, so nobody has to guess.
        entry["stale_metrics"] = sorted(
            name for name in SPECS if needs_build(root, int(season), name))
    summary = {
        "generated_at": utc_now(),
        "layout": layout,
        "schema_sha256": schema_sha256(),
        "reading": {
            "columns": "data/curated/schema.json",
            "integrity": "data/curated/partition-index.json (large; per-game digests, not for browsing)",
            "api": "visualbaseball.curated.load_rows(root, kind, season, columns=..., game_id=..., player_id=...)",
        },
        "seasons": dict(sorted(seasons.items())),
        "published": {
            "web_json": _counts(root / "web" / "data", "**/*.json"),
            "exports": _counts(root / "exports"),
        },
    }
    path = root.joinpath(*SUMMARY_PATH)
    _atomic_json(path, summary)
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    print(json.dumps(json.loads(build_summary(args.root).read_text(encoding="utf-8")), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
