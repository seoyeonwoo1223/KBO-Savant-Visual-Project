from __future__ import annotations

from pathlib import Path
from .parser import parse_game
from .storage import Store
from .validation import validate_game


def process_payload(root: Path, payload: dict, schedule_game: dict | None = None, season: int = 2026) -> tuple[bool, str, int]:
    game, events, pitches, unknown = parse_game(payload, schedule_game, season)
    valid, message = validate_game(game, events, pitches); store = Store(root); raw_path = store.write_raw(season, game["game_id"], payload)
    if valid and game["is_final"]:
        game["validation_status"] = "PASS"; store.replace_game(game, events, pitches); store.mark(game["game_id"], "completed", raw_path, message)
    else:
        game["validation_status"] = f"FAIL: {message}"; store.mark(game["game_id"], "failed" if game["is_final"] else "incomplete", raw_path, message)
    return valid and game["is_final"], message, len(pitches)
