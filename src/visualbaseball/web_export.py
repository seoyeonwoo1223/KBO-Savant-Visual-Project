"""Create small, browser-friendly derivatives from the authoritative Parquet tables."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq


GAME_COLUMNS = (
    "season", "game_date", "game_id", "away_team", "home_team", "stadium",
    "game_status", "away_score", "home_score", "validation_status",
)
MOVEMENT_COLUMNS = (
    "game_date", "game_id", "pitch_id", "pitcher_name", "batter_name",
    "pitch_type", "pitch_type_code", "velocity_kmh", "vertical_movement_cm",
    "horizontal_movement_cm", "px", "pz", "inning", "inning_half",
)


def _rows(root: Path, name: str) -> list[dict]:
    path = root / "data" / "processed" / f"{name}.parquet"
    return pq.read_table(path).to_pylist() if path.exists() else []


def _write_csv(path: Path, columns: tuple[str, ...], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def export_web_data(root: Path) -> Path:
    """Write GitHub Pages assets without making the site depend on Parquet support."""
    output = root / "web" / "data"
    output.mkdir(parents=True, exist_ok=True)
    games = _rows(root, "games")
    pitches = _rows(root, "pitches")
    events = _rows(root, "events")
    _write_csv(output / "games.csv", GAME_COLUMNS, games)
    _write_csv(output / "movement.csv", MOVEMENT_COLUMNS, pitches)
    dates = sorted(str(row.get("game_date")) for row in games if row.get("game_date"))
    summary = {
        "season": 2026,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "date_range": [dates[0], dates[-1]] if dates else [],
        "games": len(games),
        "events": len(events),
        "pitches": len(pitches),
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    export_web_data(Path(".").resolve())
