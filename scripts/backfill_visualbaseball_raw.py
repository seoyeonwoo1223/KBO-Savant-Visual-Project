"""Fetch a completed historical season and write only raw plus canonical data."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from threading import local

from visualbaseball.cli import _is_final
from visualbaseball.collector import cache_payload, prepare_game
from visualbaseball.curated import validation_summary
from visualbaseball.dataset_summary import build_summary
from visualbaseball.http_client import VisualBaseballClient
from visualbaseball.storage import Store


def backfill(root: Path, season: int, workers: int, limit: int | None = None) -> dict:
    root = root.resolve()
    store = Store(root)
    client = VisualBaseballClient()
    schedule = client.get_json(f"/api/schedule/season?y={season}")["schedule"]
    all_games = [
        (game_date, game) for game_date, games in schedule.items() for game in games
        if _is_final(game)
    ]
    targets = [
        game for game_date, game in all_games
        if store.should_fetch(game["gameId"], game_date, 7)
    ]
    if limit is not None:
        targets = targets[:limit]
    worker_state = local()

    def fetch(game: dict):
        request_client = getattr(worker_state, "client", None)
        if request_client is None:
            request_client = VisualBaseballClient()
            worker_state.client = request_client
        game_id = game["gameId"]
        payload = request_client.get_json(f"/api/game/pbp?id={game_id}", f"/game/{game_id}/pbp")
        return prepare_game(payload, season=season), payload

    completed = failed = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = [executor.submit(fetch, game) for game in targets]
        for index, future in enumerate(as_completed(futures), 1):
            prepared, payload = future.result()
            raw_path = cache_payload(store, season, payload, prepared)
            if raw_path is None:
                failed += 1
            else:
                store.replace_game(prepared.game, prepared.events, prepared.pitches)
                store.mark(prepared.game["game_id"], "completed", raw_path, prepared.message)
                completed += 1
            if index % 25 == 0 or index == len(futures):
                print(f"Visual Baseball {season}: {index}/{len(futures)} games", flush=True)

    result = {"season": season, "scheduled_games": len(all_games), "fetched": len(targets), "completed": completed, "failed": failed}
    if limit is None:
        validation = validation_summary(root, season)
        if validation["pitch_id_duplicates"] or validation["raw_pitches"] != validation["curated_pitches"] + validation["parse_excluded"]:
            raise ValueError(f"season {season}: canonical validation failed: {validation}")
        build_summary(root)
        result["validation"] = validation
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    print(backfill(args.root, args.season, args.workers, args.limit))


if __name__ == "__main__":
    main()
