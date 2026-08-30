from __future__ import annotations

import argparse, json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import local

from .collector import _load_naver, cache_payload, prepare_game, process_payload, rebuild_from_raw
from .export_excel import export_latest
from .web_export import export_web_data
from .http_client import VisualBaseballClient
from .storage import Store
from .swing_take import build_swing_take
from .zone_profile import build_zone_profiles
from .blocking import build_blocking
from .pitch_arsenal import build_pitch_arsenal


def _exports(root: Path, season: int, storage_root: Path) -> None:
    # Publish source tables first, then derive all Swing/Take artifacts from
    # the workbook's Pitches sheet. Derived decision rows stay out of Excel.
    workbook = export_latest(root, season, storage_root)
    build_swing_take(storage_root, season, excel_source=workbook)
    build_zone_profiles(root, season, excel_source=workbook)
    build_pitch_arsenal(root, season, excel_source=workbook)
    build_blocking(root, season, storage_root)
    if storage_root == root:
        export_web_data(root)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--storage-root")
    parser.add_argument("--fixture")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--game-id")
    parser.add_argument("--rebuild-from-raw", action="store_true")
    parser.add_argument("--refresh-completed", action="store_true")
    parser.add_argument(
        "--refresh-workers",
        type=int,
        default=1,
        help="Concurrent Visual Baseball PBP fetches; keep 1 for ordinary daily updates.",
    )
    parser.add_argument(
        "--refresh-naver",
        action="store_true",
        help="Fetch and cache Naver relay flags while rebuilding raw games",
    )
    parser.add_argument("--naver-workers", type=int, default=1)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    storage_root = Path(args.storage_root).resolve() if args.storage_root else root
    if args.rebuild_from_raw:
        games, pitches = rebuild_from_raw(
            storage_root, args.season, args.refresh_naver, args.game_id, max(1, args.naver_workers)
        )
        _exports(root, args.season, storage_root)
        print(f"rebuilt {games} games and {pitches} pitches")
        return
    if args.fixture:
        payload = json.loads(Path(args.fixture).read_text(encoding="utf-8-sig"))
        ok, message, pitches = process_payload(storage_root, payload, season=args.season)
        if not ok:
            raise SystemExit(message)
        _exports(root, args.season, storage_root)
        print(f"processed {pitches} pitches")
        return

    client = VisualBaseballClient()
    store = Store(storage_root)
    schedule = client.get_json(f"/api/schedule/season?y={args.season}")["schedule"]
    target_games: list[dict] = []
    for game_date, games in schedule.items():
        for game in games:
            if args.game_id and game.get("gameId") != args.game_id:
                continue
            status = str(game.get("status", ""))
            if status.lower() not in {"final", "finished", "end"} and (chr(0xC885) + chr(0xB8CC)) not in status:
                continue
            if not args.refresh_completed and not store.should_fetch(game["gameId"], game_date):
                continue
            target_games.append(game)

    def fetch_game(game: dict, request_client: VisualBaseballClient) -> tuple[object, dict]:
        game_id = game["gameId"]
        payload = request_client.get_json(f"/api/game/pbp?id={game_id}", f"/game/{game_id}/pbp")
        innings = max((int(half.get("inning") or 0) for half in payload.get("pbpData", [])), default=9)
        naver_enrichment = _load_naver(store, args.season, game_id, innings, None, args.refresh_naver)
        if naver_enrichment is None:
            # New final games get the supplementary flags as part of the
            # ordinary daily pass; a later raw rebuild can retry failures.
            from .naver import NaverSportsClient
            naver_enrichment = _load_naver(
                store, args.season, game_id, innings, NaverSportsClient(), args.refresh_naver
            )
        return prepare_game(payload, game, args.season, naver_enrichment), payload

    workers = max(1, args.refresh_workers)
    fetched: list[tuple[object, dict] | None] = [None] * len(target_games)
    if workers == 1:
        for index, game in enumerate(target_games, 1):
            fetched[index - 1] = fetch_game(game, client)
            if index % 25 == 0 or index == len(target_games):
                print(f"Visual Baseball fetch: {index}/{len(target_games)} games", flush=True)
    else:
        worker_state = local()

        def threaded_fetch(game: dict) -> tuple[object, dict]:
            request_client = getattr(worker_state, "client", None)
            if request_client is None:
                request_client = VisualBaseballClient()
                worker_state.client = request_client
            return fetch_game(game, request_client)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(threaded_fetch, game): index
                for index, game in enumerate(target_games)
            }
            for completed, future in enumerate(as_completed(futures), 1):
                fetched[futures[future]] = future.result()
                if completed % 25 == 0 or completed == len(futures):
                    print(f"Visual Baseball fetch: {completed}/{len(futures)} games", flush=True)

    pending_games, pending_events, pending_pitches, pending_completions = [], [], [], []

    def flush() -> None:
        nonlocal pending_games, pending_events, pending_pitches, pending_completions
        store.replace_games(pending_games, pending_events, pending_pitches)
        for prepared, raw_path in pending_completions:
            store.mark(prepared.game["game_id"], "completed", raw_path, prepared.message)
        pending_games, pending_events, pending_pitches, pending_completions = [], [], [], []

    for result in fetched:
        prepared, payload = result
        raw_path = cache_payload(store, args.season, payload, prepared)
        if raw_path:
            pending_games.append(prepared.game)
            pending_events.extend(prepared.events)
            pending_pitches.extend(prepared.pitches)
            pending_completions.append((prepared, raw_path))
            if len(pending_games) >= 25:
                flush()
    flush()
    _exports(root, args.season, storage_root)


if __name__ == "__main__":
    main()
