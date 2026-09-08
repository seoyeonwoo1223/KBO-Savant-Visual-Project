"""Create an immutable, versioned ZA input without changing legacy data."""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .za_inputs import _safe_version, _sha256

sha256 = _sha256


def inventory(root: Path, season: int) -> dict:
    """Return the Phase 1/2 inventory without writing anything."""
    legacy = (root / "data/processed/pitches.parquet" if season == 2026 else
              root / "exports" / f"visualbaseball_savant_{season}_latest.xlsx")
    events = legacy.with_name("events.parquet") if season == 2026 else None
    raw = root / "data/raw" / str(season)
    return {
        "season": season,
        "legacy_source": str(legacy.relative_to(root)),
        "legacy_exists": legacy.is_file(),
        "legacy_sha256": sha256(legacy) if legacy.is_file() else None,
        "events_source": str(events.relative_to(root)) if events else None,
        "events_exists": events.is_file() if events else None,
        "events_sha256": sha256(events) if events and events.is_file() else None,
        "raw_json_files": sum(1 for _ in raw.glob("*.json")) if raw.is_dir() else 0,
    }


def curate(root: Path, season: int, version: str, source: Path | None = None,
           events_source: Path | None = None) -> Path:
    """Copy one complete legacy ZA source set into a new curated version."""
    version = _safe_version(version)
    source = source or (root / "data/processed/pitches.parquet" if season == 2026 else
                        root / "exports" / f"visualbaseball_savant_{season}_latest.xlsx")
    events_source = events_source or (source.with_name("events.parquet") if season == 2026 else None)
    for required in (source, events_source):
        if required is not None and not required.is_file():
            raise FileNotFoundError(required)
    destination = root / "data/curated/zone_awareness" / version
    if destination.exists():
        raise FileExistsError(f"curated ZA version is immutable: {destination}")
    destination.mkdir(parents=True)
    artifact = destination / source.name
    shutil.copy2(source, artifact)
    entry = {"path": artifact.name, "sha256": sha256(artifact)}
    if events_source:
        events_artifact = destination / events_source.name
        shutil.copy2(events_source, events_artifact)
        entry.update({"events_path": events_artifact.name, "events_sha256": sha256(events_artifact)})
    manifest = {
        "schema_version": 1,
        "version": version,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "seasons": {str(season): entry},
    }
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("inventory", "curate"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--version")
    parser.add_argument("--source")
    parser.add_argument("--events-source")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if args.command == "inventory":
        print(json.dumps(inventory(root, args.season), indent=2))
        return
    if not args.version:
        parser.error("curate requires --version")
    source = Path(args.source).resolve() if args.source else None
    events_source = Path(args.events_source).resolve() if args.events_source else None
    print(curate(root, args.season, args.version, source, events_source))


if __name__ == "__main__":
    main()
