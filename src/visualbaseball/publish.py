"""JSON publication helpers shared by the metric builders.

Everything written here is output only (web/data, data/metrics reports); no code reads it
back as input. Byte layout is part of the web contract: compact files use ``(",", ":")``
separators, catalogs use two-space indentation, and every file ends with a newline.
"""
from __future__ import annotations

import json
from pathlib import Path


def write_json(path: Path, payload, *, compact: bool = True, allow_nan: bool = True) -> None:
    options = {"separators": (",", ":")} if compact else {"indent": 2}
    path.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=allow_nan, **options) + "\n", encoding="utf-8")


def write_shards(directory: Path, shards: dict[str, dict]) -> None:
    """Write ``<shard>.json`` files and delete shards that no longer exist."""
    directory.mkdir(parents=True, exist_ok=True)
    for shard, payload in shards.items():
        write_json(directory / f"{shard}.json", payload)
    for stale in directory.glob("*.json"):
        if stale.stem not in shards:
            stale.unlink()


def add_catalog_season(path: Path, season: int) -> None:
    """Add ``season`` to a page's ``{"seasons": [...]}`` catalog, newest first."""
    catalog = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"seasons": []}
    catalog["seasons"] = sorted({*catalog.get("seasons", []), season}, reverse=True)
    write_json(path, catalog, compact=False)
