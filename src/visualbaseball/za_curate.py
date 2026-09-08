"""Create an immutable, versioned ZA input without changing legacy data."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .za_inputs import _safe_version


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inventory(root: Path, season: int) -> dict:
    """Return the Phase 1/2 inventory without writing anything."""
    legacy = (root / "data/processed/pitches.parquet" if season == 2026 else
              root / "exports" / f"visualbaseball_savant_{season}_latest.xlsx")
    raw = root / "data/raw" / str(season)
    return {
        "season": season,
        "legacy_source": str(legacy.relative_to(root)),
        "legacy_exists": legacy.is_file(),
        "legacy_sha256": sha256(legacy) if legacy.is_file() else None,
        "raw_json_files": sum(1 for _ in raw.glob("*.json")) if raw.is_dir() else 0,
    }


def curate(root: Path, season: int, version: str, source: Path | None = None) -> Path:
    """Copy one legacy source into a new curated version and write its manifest."""
    version = _safe_version(version)
    source = source or (root / "data/processed/pitches.parquet" if season == 2026 else
                        root / "exports" / f"visualbaseball_savant_{season}_latest.xlsx")
    if not source.is_file():
        raise FileNotFoundError(source)
    destination = root / "data/curated/zone_awareness" / version
    if destination.exists():
        raise FileExistsError(f"curated ZA version is immutable: {destination}")
    destination.mkdir(parents=True)
    artifact = destination / source.name
    shutil.copy2(source, artifact)
    manifest = {
        "schema_version": 1,
        "version": version,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "seasons": {str(season): {"path": artifact.name, "sha256": sha256(artifact)}},
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
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if args.command == "inventory":
        print(json.dumps(inventory(root, args.season), indent=2))
        return
    if not args.version:
        parser.error("curate requires --version")
    source = Path(args.source).resolve() if args.source else None
    print(curate(root, args.season, args.version, source))


if __name__ == "__main__":
    main()
