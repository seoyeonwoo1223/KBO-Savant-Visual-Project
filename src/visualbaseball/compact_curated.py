"""One-time game-shard to monthly-partition migration."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import pyarrow.parquet as pq

from .curated import SCHEMAS, _atomic_parquet, _atomic_json, _month, _stable_rows, value_sha256


def compact(root: Path, season: int) -> dict:
    root = root.resolve()
    index_path = root / "data" / "curated" / "partition-index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {"schema_version": 1, "seasons": {}}
    directories = [root / "data" / "curated" / kind / f"season={season}" for kind in SCHEMAS]
    months = {str(entry.get("month")) for entry in index.get("seasons", {}).get(str(season), {}).get("games", {}).values()}
    if (index.get("layout") == "month" and str(season) in index.get("seasons", {})
            and months and all(all((directory / f"month={month}.parquet").is_file() for month in months) for directory in directories)):
        for directory in directories:
            for path in directory.glob("*.parquet"):
                if not path.name.startswith("month="): path.unlink()
        return {"season": season, "changed": 0, "reason": "already compact"}
    manifests = sorted((root / "data" / "curated" / "sources" / f"season={season}").glob("*.json"))
    games = {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in manifests}
    entries, groups = {}, {kind: defaultdict(list) for kind in SCHEMAS}
    for game_id, manifest in games.items():
        game_rows = {}
        for kind, schema in SCHEMAS.items():
            path = root / "data" / "curated" / kind / f"season={season}" / f"{game_id}.parquet"
            if not path.exists():
                raise FileNotFoundError(path)
            game_rows[kind] = pq.ParquetFile(path).read().to_pylist()
        game = game_rows["games"][0] if game_rows["games"] else {"game_id": game_id}
        month = _month(game)
        entries[game_id] = {"game_date": game.get("game_date"), "month": month, "revision": manifest.get("revision", 0),
                            "tables": {kind: value_sha256(_stable_rows(rows)) for kind, rows in game_rows.items()}}
        for kind, rows in game_rows.items(): groups[kind][month].extend(rows)
    for kind, months in groups.items():
        directory = root / "data" / "curated" / kind / f"season={season}"
        for month, rows in months.items(): _atomic_parquet(directory / f"month={month}.parquet", rows, SCHEMAS[kind])
    # Commit the layout before removal: interruption before this point retains all
    # legacy shards; after it, all compact partitions are already durable.
    index["layout"] = "month"; index.setdefault("seasons", {}).setdefault(str(season), {})["games"] = entries
    _atomic_json(index_path, index)
    for kind in SCHEMAS:
        for path in (root / "data" / "curated" / kind / f"season={season}").glob("*.parquet"):
            if not path.name.startswith("month="): path.unlink()
    return {"season": season, "changed": len(entries), "partitions": sum(len(value) for value in groups.values())}


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--root", type=Path, default=Path(".")); parser.add_argument("--season", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(compact(args.root, args.season), indent=2))


if __name__ == "__main__": main()
