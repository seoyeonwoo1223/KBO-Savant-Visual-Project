"""Batting-club lookup shared by the plate-decision metrics."""
from __future__ import annotations


TEAM_CODES = {
    "두산": "DOO", "삼성": "SAM", "키움": "KIW", "롯데": "LOT", "한화": "HAN",
    "KIA": "KIA", "KT": "KT", "LG": "LG", "NC": "NC", "SSG": "SSG",
}
# VB game IDs retain the historical two-letter club code, including the former
# SK code used before the SSG rename.  This keeps archived season exports
# independent from the much smaller leaderboard source tables.
GAME_TEAM_CODES = {
    "OB": "DOO", "SS": "SAM", "WO": "KIW", "LT": "LOT", "HH": "HAN",
    "HT": "KIA", "SK": "SSG", "LG": "LG", "NC": "NC", "KT": "KT",
}


def team_code(row: dict) -> str | None:
    """Return the batting club for a source row, without guessing by name."""
    direct = str(row.get("batter_team") or "").strip()
    if direct:
        return TEAM_CODES.get(direct, direct if direct in TEAM_CODES.values() else None)
    game_id, half = str(row.get("game_id") or ""), str(row.get("inning_half") or "")
    if len(game_id) >= 12 and half in {"top", "bottom"}:
        raw_code = game_id[8:10] if half == "top" else game_id[10:12]
        return GAME_TEAM_CODES.get(raw_code)
    return None


def team_history(items: list[dict]) -> str:
    """Join each club a batter represented in first-appearance order."""
    teams: list[str] = []
    for item in sorted(items, key=lambda row: (str(row.get("game_date") or row.get("game_id") or ""), int(row.get("event_seq") or 0))):
        team = team_code(item)
        if team and team not in teams:
            teams.append(team)
    return " · ".join(teams) if teams else "—"
