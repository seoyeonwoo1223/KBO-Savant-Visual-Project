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


def cache_payload(store: Store, season: int, payload: dict, prepared: PreparedGame) -> Path | None:
    """Persist raw source; completed games are marked only after table writes succeed."""
    raw_path = store.write_raw(season, prepared.game["game_id"], payload)
    if not prepared.completed:
        status = "failed" if prepared.game["is_final"] else "incomplete"
        store.mark(prepared.game["game_id"], status, raw_path, prepared.message)
        return None
    return raw_path


def process_payload(root: Path, payload: dict, schedule_game: dict | None = None, season: int = 2026) -> tuple[bool, str, int]:
    prepared = prepare_game(payload, schedule_game, season)
    store = Store(root)
    raw_path = cache_payload(store, season, payload, prepared)
    if raw_path:
        store.replace_game(prepared.game, prepared.events, prepared.pitches)
        store.mark(prepared.game["game_id"], "completed", raw_path, prepared.message)
    return raw_path is not None, prepared.message, len(prepared.pitches)
