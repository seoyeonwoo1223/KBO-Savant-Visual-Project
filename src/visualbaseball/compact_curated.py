"""One-time game-shard to monthly-partition migration."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .curated import (SCHEMAS, _atomic_parquet, _atomic_json, _month, _monthly_files_valid,
                      _monthly_path, table_digest)


class CompactionError(RuntimeError):
    """A monthly partition did not match the index; legacy shards are retained."""


def _legacy_shards(root: Path, season: int) -> list[Path]:
    return [path for kind in SCHEMAS
            for path in (root / "data" / "curated" / kind / f"season={season}").glob("*.parquet")
            if not path.name.startswith("month=")]


def _legacy_complete(root: Path, season: int, indexed: dict) -> bool:
    """True when every indexed game still has all three legacy shards on disk."""
    return bool(indexed) and all(
        (root / "data" / "curated" / kind / f"season={season}" / f"{game_id}.parquet").is_file()
        for game_id in indexed for kind in SCHEMAS)


def _rows_by_game(root: Path, kind: str, season: int, month: str) -> dict[str, list[dict]]:
    path = _monthly_path(root, kind, season, month)
    grouped: dict[str, list[dict]] = defaultdict(list)
    try:
        rows = pq.ParquetFile(path).read().to_pylist()
    except (OSError, pa.ArrowException) as error:
        raise CompactionError(f"unreadable partition {path}: {error}") from error
    for row in rows:
        grouped[str(row.get("game_id"))].append(row)
    return grouped


def verify_partitions(root: Path, season: int, entries: dict) -> None:
    """Read every expected partition back and match it against the index digests.

    A footer/schema probe still succeeds when only data pages are damaged, so the
    migration never treats `_monthly_files_valid` as proof that a month is intact.
    Only a full read plus a per-game digest comparison can retire a legacy shard.
    """
    months = sorted({str(entry["month"]) for entry in entries.values()})
    if not months:
        raise CompactionError(f"season={season} has no indexed months to verify")
    for month in months:
        if not _monthly_files_valid(root, season, month):
            raise CompactionError(f"missing or unreadable partition for season={season} month={month}")
    for kind, schema in SCHEMAS.items():
        for month in months:
            grouped = _rows_by_game(root, kind, season, month)
            for game_id, entry in entries.items():
                if str(entry["month"]) != month:
                    continue
                digest = table_digest(grouped.get(game_id, []), schema)
                if digest != entry["tables"][kind]:
                    raise CompactionError(
                        f"partition {kind}/season={season}/month={month} does not match the index "
                        f"for {game_id}; legacy shards are retained")


def compact(root: Path, season: int) -> dict:
    root = root.resolve()
    index_path = root / "data" / "curated" / "partition-index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {"schema_version": 1, "seasons": {}}
    indexed = index.get("seasons", {}).get(str(season), {}).get("games", {})
    if index.get("layout") == "month" and indexed:
        # Resuming after an interruption between the index switch and cleanup.
        try:
            verify_partitions(root, season, indexed)
        except CompactionError:
            # Only rebuild when every legacy shard is still on disk; otherwise the
            # damage is unrecoverable here and must not be papered over.
            if not _legacy_complete(root, season, indexed):
                raise
        else:
            for path in _legacy_shards(root, season):
                path.unlink()
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
                            "tables": {kind: table_digest(rows, SCHEMAS[kind]) for kind, rows in game_rows.items()}}
        for kind, rows in game_rows.items(): groups[kind][month].extend(rows)
    for kind, months in groups.items():
        directory = root / "data" / "curated" / kind / f"season={season}"
        for month, rows in months.items(): _atomic_parquet(directory / f"month={month}.parquet", rows, SCHEMAS[kind])
    # Nothing is retired until the new partitions read back byte-for-byte. Aborting
    # here leaves the season on its legacy shards with the index still on "game".
    verify_partitions(root, season, entries)
    index["layout"] = "month"; index.setdefault("seasons", {}).setdefault(str(season), {})["games"] = entries
    _atomic_json(index_path, index)
    # Re-verify against the committed index: the window between the two passes is
    # exactly where a partial write would otherwise cost the legacy copies.
    verify_partitions(root, season, entries)
    for path in _legacy_shards(root, season):
        path.unlink()
    return {"season": season, "changed": len(entries), "partitions": sum(len(value) for value in groups.values())}


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--root", type=Path, default=Path(".")); parser.add_argument("--season", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(compact(args.root, args.season), indent=2))


if __name__ == "__main__": main()
