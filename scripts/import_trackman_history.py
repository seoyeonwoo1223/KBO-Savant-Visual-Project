"""Split one TrackMan history CSV into year-scoped, reproducible raw files."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from uuid import uuid4


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def import_history(source: Path, root: Path) -> dict:
    source = source.resolve()
    destination_root = root / "data" / "tracking" / "raw"
    writers: dict[str, csv.writer] = {}
    handles = {}
    temporary_paths: dict[str, Path] = {}
    row_counts: dict[str, int] = {}
    try:
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            if not header or "season" not in header:
                raise ValueError("TrackMan CSV must have a season column")
            season_index = header.index("season")
            for row_number, row in enumerate(reader, 2):
                if len(row) != len(header):
                    raise ValueError(f"row {row_number}: expected {len(header)} columns, got {len(row)}")
                season = row[season_index]
                if not (season.isdigit() and len(season) == 4):
                    raise ValueError(f"row {row_number}: invalid season {season!r}")
                if season not in writers:
                    destination = destination_root / f"season={season}" / "trackman_history.csv"
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    temporary = destination.with_name(destination.name + f".{uuid4().hex}.tmp")
                    output = temporary.open("w", encoding="utf-8", newline="")
                    writers[season] = csv.writer(output, lineterminator="\n")
                    writers[season].writerow(header)
                    handles[season] = output
                    temporary_paths[season] = temporary
                    row_counts[season] = 0
                writers[season].writerow(row)
                row_counts[season] += 1
    finally:
        for handle in handles.values():
            handle.close()

    files = {}
    for season, temporary in temporary_paths.items():
        destination = destination_root / f"season={season}" / "trackman_history.csv"
        temporary.replace(destination)
        with destination.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            output_header = next(reader, None)
            output_rows = 0
            for row in reader:
                if len(row) != len(header) or row[season_index] != season:
                    raise ValueError(f"season={season}: split verification failed")
                output_rows += 1
        if output_header != header or output_rows != row_counts[season]:
            raise ValueError(f"season={season}: split verification failed")
        files[season] = {
            "rows": row_counts[season],
            "bytes": destination.stat().st_size,
            "sha256": _sha256(destination),
            "path": destination.relative_to(root).as_posix(),
        }
    result = {
        "source_sha256": _sha256(source),
        "columns": header,
        "rows": sum(row_counts.values()),
        "seasons": {season: files[season] for season in sorted(files)},
    }
    _write_json(root / "data" / "tracking" / "summary.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    print(json.dumps(import_history(args.source, args.root.resolve()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
