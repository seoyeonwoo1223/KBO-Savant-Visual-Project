from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
import json
from .naver import NaverEnrichment, NaverSportsClient
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


def prepare_game(payload: dict, schedule_game: dict | None = None, season: int = 2026, naver_enrichment: NaverEnrichment | None = None) -> PreparedGame:
    game, events, pitches, _ = parse_game(payload, schedule_game, season, naver_enrichment)
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


def process_payload(root: Path, payload: dict, schedule_game: dict | None = None, season: int = 2026, naver_enrichment: NaverEnrichment | None = None) -> tuple[bool, str, int]:
    prepared = prepare_game(payload, schedule_game, season, naver_enrichment)
    store = Store(root)
    raw_path = cache_payload(store, season, payload, prepared)
    if raw_path:
        store.replace_game(prepared.game, prepared.events, prepared.pitches)
        store.mark(prepared.game["game_id"], "completed", raw_path, prepared.message)
    return raw_path is not None, prepared.message, len(prepared.pitches)


def _load_naver(store: Store, season: int, game_id: str, innings: int, client: NaverSportsClient | None, refresh: bool) -> NaverEnrichment | None:
    cached = None if refresh else store.read_naver(season, game_id)
    if cached:
        return NaverEnrichment.from_dict(cached)
    if not client:
        return None
    try:
        enrichment = client.fetch_enrichment(game_id, season, innings)
        store.write_naver(season, game_id, enrichment.to_dict())
        return enrichment
    except RuntimeError as error:
        # VB rows remain usable when the supplementary source is temporarily
        # unavailable; the nullable match fields make that absence explicit.
        print(f"Naver enrichment unavailable for {game_id}: {error}")
        return None


def rebuild_from_raw(root: Path, season: int = 2026, refresh_naver: bool = False, game_id: str | None = None) -> tuple[int, int]:
    """Reparse retained source payloads after a schema or parser change."""
    store = Store(root)
    requested_game_id = game_id
    completed: list[tuple[PreparedGame, Path]] = []
    naver_client = NaverSportsClient() if refresh_naver else None
    for path in sorted((root / "data" / "raw" / str(season)).glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        current_game_id = str(payload.get("gameData", {}).get("gameId", path.stem))
        if requested_game_id and current_game_id != requested_game_id:
            continue
        innings = max((int(half.get("inning") or 0) for half in payload.get("pbpData", [])), default=9)
        naver_enrichment = _load_naver(store, season, current_game_id, innings, naver_client, refresh_naver)
        prepared = prepare_game(payload, season=season, naver_enrichment=naver_enrichment)
        raw_path = cache_payload(store, season, payload, prepared)
        if raw_path:
            completed.append((prepared, raw_path))
    store.replace_games(
        [prepared.game for prepared, _ in completed],
        [event for prepared, _ in completed for event in prepared.events],
        [pitch for prepared, _ in completed for pitch in prepared.pitches],
    )
    for prepared, raw_path in completed:
        store.mark(prepared.game["game_id"], "completed", raw_path, prepared.message)
    return len(completed), sum(len(prepared.pitches) for prepared, _ in completed)
