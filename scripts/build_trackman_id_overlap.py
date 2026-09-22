"""Write the exact same-season player IDs shared by TrackMan and Visual Baseball."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import uuid4

import pandas as pd

from visualbaseball.curated import load_rows


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _ids(rows: list[dict], field: str) -> set[str]:
    return {str(row[field]) for row in rows if row.get(field) not in (None, "")}


def build(root: Path) -> dict:
    result = {"schema_version": 1, "join": "same-season string equality", "seasons": {}}
    for season_path in sorted((root / "data" / "tracking" / "raw").glob("season=*")):
        season = int(season_path.name.removeprefix("season="))
        source = season_path / "trackman_history.csv"
        tracking = pd.read_csv(source, usecols=["pitcher_trackman_id", "batter_trackman_id"])
        trackman = {
            "pitcher": {str(value) for value in tracking["pitcher_trackman_id"].dropna().astype("int64")},
            "batter": {str(value) for value in tracking["batter_trackman_id"].dropna().astype("int64")},
        }
        pitches = load_rows(root, "pitches", season, columns=["pitcher_id", "batter_id"])
        visualbaseball = {"pitcher": _ids(pitches, "pitcher_id"), "batter": _ids(pitches, "batter_id")}
        entry = {"trackman_rows": len(tracking), "roles": {}}
        for role in ("pitcher", "batter"):
            shared = sorted(trackman[role] & visualbaseball[role], key=int)
            entry["roles"][role] = {
                "trackman_unique_ids": len(trackman[role]),
                "visualbaseball_unique_ids": len(visualbaseball[role]),
                "shared_unique_ids": len(shared),
                "trackman_match_rate": round(len(shared) / len(trackman[role]), 6) if trackman[role] else None,
                "shared_ids": shared,
            }
        result["seasons"][str(season)] = entry
    _write_json(root / "data" / "tracking" / "player_id_overlap.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    print(json.dumps(build(args.root.resolve()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
