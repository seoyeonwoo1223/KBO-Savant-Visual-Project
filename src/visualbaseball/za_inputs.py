"""Compatibility resolver for the single canonical ZA input."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .curated import schema_sha256


INPUT_MODES = ("curated",)


@dataclass(frozen=True)
class ZAInput:
    mode: str
    path: Path
    events_path: Path
    version: None
    sha256: str
    events_sha256: str


def resolve_za_input(root: Path, season: int, mode: str | None = None,
                     version: str | None = None, storage_root: Path | None = None) -> ZAInput:
    """Resolve canonical shards; there is deliberately no legacy fallback."""
    if mode not in {None, "curated"}:
        raise ValueError("ZA only accepts the canonical curated dataset")
    if version:
        raise ValueError("versioned ZA copies were replaced by canonical game shards")
    pitches = root / "data" / "curated" / "pitches" / f"season={season}"
    events = root / "data" / "curated" / "events" / f"season={season}"
    if not any(pitches.glob("*.parquet")) or not any(events.glob("*.parquet")):
        raise FileNotFoundError(f"canonical curated input is missing for season {season}")
    digest = schema_sha256()
    return ZAInput("curated", pitches, events, None, digest, digest)
