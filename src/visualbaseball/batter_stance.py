"""Batter handedness lookup and per-pitch batting side."""
from __future__ import annotations

from pathlib import Path

import pyarrow.parquet as pq

from .curated import _number


def load_batter_hands(root: Path) -> dict[str, str]:
    """Load handedness from the canonical player dimension."""
    source = root / "data" / "curated" / "players" / "player_bio.parquet"
    if not source.exists():
        return {}
    return {str(row["player_id"]): str(row.get("bats") or "") for row in pq.read_table(source, columns=["player_id", "bats"]).to_pylist()}


def resolved_batter_stance(row: dict, batter_hands: dict[str, str]) -> str:
    stance = str(row.get("batter_stance") or "").strip().upper()
    if stance in {"L", "R"}:
        return stance
    bats = batter_hands.get(str(row.get("batter_id") or "").strip(), "")
    if bats in {"L", "R"}:
        return bats
    if bats == "S":
        release_x = _number(row.get("release_x_50"))
        if release_x is not None and abs(release_x) >= 0.1:
            return "L" if release_x < 0 else "R"
    return ""
