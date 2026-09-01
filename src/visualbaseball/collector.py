from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    cached = store.read_naver(season, game_id)
    if cached:
        enrichment = NaverEnrichment.from_dict(cached)
        if not refresh or enrichment.coverage == "record_no_event":
            return enrichment
    if not client:
        return None
    try:
        enrichment = client.fetch_enrichment(game_id, season, innings)
        store.write_naver(season, game_id, enrichment.to_dict())
        return enrichment
    except RuntimeError as error:
        print(f"Naver enrichment unavailable for {game_id}: {error}")
        return None


def rebuild_from_raw(root: Path, season: int = 2026, refresh_naver: bool = False, game_id: str | None = None, naver_workers: int = 1) -> tuple[int, int]:
    """Reparse retained source payloads after a schema or parser change."""
    store = Store(root)
    requested_game_id = game_id
    completed: list[tuple[PreparedGame, Path]] = []
    paths = sorted((root / "data" / "raw" / str(season)).glob("*.json"))
    if requested_game_id:
        paths = [path for path in paths if path.stem == requested_game_id]
    prefetched: dict[Path, NaverEnrichment | None] = {}
    if refresh_naver and naver_workers > 1:
        def fetch(path: Path) -> tuple[Path, NaverEnrichment | None]:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            current_game_id = str(payload.get("gameData", {}).get("gameId", path.stem))
            innings = max((int(half.get("inning") or 0) for half in payload.get("pbpData", [])), default=9)
            return path, _load_naver(store, season, current_game_id, innings, NaverSportsClient(), True)
        with ThreadPoolExecutor(max_workers=naver_workers) as executor:
            futures = [executor.submit(fetch, path) for path in paths]
            for count, future in enumerate(as_completed(futures), 1):
                path, enrichment = future.result(); prefetched[path] = enrichment
                if count % 25 == 0 or count == len(futures):
                    print(f"Naver enrichment: {count}/{len(futures)} games")
    naver_client = NaverSportsClient() if refresh_naver and naver_workers <= 1 else None
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        current_game_id = str(payload.get("gameData", {}).get("gameId", path.stem))
        innings = max((int(half.get("inning") or 0) for half in payload.get("pbpData", [])), default=9)
        naver_enrichment = prefetched.get(path) if path in prefetched else _load_naver(store, season, current_game_id, innings, naver_client, refresh_naver)
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
