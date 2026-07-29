from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
from .parser import parse_game
from .storage import Store
from .validation import validate_game


@dataclass
class PreparedGame:
    """Parsed payload plus its validation result, ready for durable storage."""

    game: dict
    events: list[dict]
    pitches: list[dict]
    valid: bool
    message: str

    @property
    def completed(self) -> bool:
        return self.valid and self.game["is_final"]


def prepare_game(payload: dict, schedule_game: dict | None = None, season: int = 2026) -> PreparedGame:
    game, events, pitches, _ = parse_game(payload, schedule_game, season)
    valid, message = validate_game(game, events, pitches)
    game["validation_status"] = "PASS" if valid and game["is_final"] else f"FAIL: {message}"
    return PreparedGame(game, events, pitches, valid, message)


def cache_and_mark(store: Store, season: int, payload: dict, prepared: PreparedGame) -> bool:
    """Persist raw source and manifest state; callers batch successful table writes."""
    raw_path = store.write_raw(season, prepared.game["game_id"], payload)
    if prepared.completed:
        store.mark(prepared.game["game_id"], "completed", raw_path, prepared.message)
        return True
    status = "failed" if prepared.game["is_final"] else "incomplete"
    store.mark(prepared.game["game_id"], status, raw_path, prepared.message)
    return False


def process_payload(root: Path, payload: dict, schedule_game: dict | None = None, season: int = 2026) -> tuple[bool, str, int]:
    prepared = prepare_game(payload, schedule_game, season)
    store = Store(root)
    completed = cache_and_mark(store, season, payload, prepared)
    if completed:
        store.replace_game(prepared.game, prepared.events, prepared.pitches)
    return completed, prepared.message, len(prepared.pitches)
