from __future__ import annotations

import argparse, json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from threading import local

import pyarrow.parquet as pq

from .collector import _load_naver, cache_payload, prepare_game, process_payload, rebuild_from_raw
from .export_excel import export_latest
from .http_client import VisualBaseballClient
from .storage import Store
from .swing_take import build_swing_take
from .zone_profile import build_zone_profiles
from .blocking import build_blocking
from .pitch_arsenal import build_pitch_arsenal
from .plate_discipline import build_plate_discipline
from .plate_decision_v1 import build_plate_decision_v1
from .zone_decision import build_zone_decision
from .arm_angle import build_arm_angle_input
from .curated import normalize_trajectory, pitch_sha256, schema_sha256, source_manifest_path
from .metric_state import mark_built, needs_build


def _is_final(game: dict) -> bool:
    status = str(game.get("status", ""))
    return status.lower() in {"final", "finished", "end"} or (chr(0xC885) + chr(0xB8CC)) in status


def select_target_games(schedule: dict, store: Store, season: int, mode: str = "recent",
                        game_id: str | None = None, today: date | None = None) -> list[dict]:
    """Select recent, eight time-stratified samples, or every completed game."""
    today = today or date.today()
    all_games = []
    for game_date, games in schedule.items():
        for game in games:
            if game_id and game.get("gameId") != game_id:
                continue
            all_games.append((date.fromisoformat(game_date), game))
    completed = [item for item in all_games if _is_final(item[1])]
    if mode == "reconcile":
        return [game for _, game in completed]
    if mode == "sample":
        eligible = [item for item in completed if (today - item[0]).days > 30]
        if len(eligible) <= 8:
            return [game for _, game in eligible]
        indexes = sorted({round(index * (len(eligible) - 1) / 7) for index in range(8)})
        return [eligible[index][1] for index in indexes]
    manifest = store.manifest().get("games", {})
    return [
        game for game_date, game in all_games
        if (game_date <= today and (
            store.should_fetch(game["gameId"], game_date.isoformat(), 7) if _is_final(game)
            else manifest.get(game["gameId"], {}).get("status") in {None, "incomplete", "failed"}
        ))
    ]


def _exports(root: Path, season: int, storage_root: Path) -> None:
    def build(name, action):
        if needs_build(root, season, name):
            action(); mark_built(root, season, name)
            print(f"built {name}", flush=True)
        else:
            print(f"unchanged {name}", flush=True)

    build("excel", lambda: export_latest(root, season))
    build("arm_angle", lambda: build_arm_angle_input(root, season))
    build("swing_take", lambda: build_swing_take(root, season))
    decision_source = root / "data" / "metrics" / "swing_take" / str(season) / (
        "decision_pitches.parquet" if season == 2026 else f"decision_pitches_{season}.parquet"
    )
    if decision_source.exists():
        build("plate_discipline", lambda: build_plate_discipline(root, season, decision_source))
        if pq.read_metadata(decision_source).num_rows >= 1_000:
            if season in (2024, 2025, 2026):
                build("zone_decision", lambda: build_zone_decision(root, season))
            else:
                build("plate_decision", lambda: build_plate_decision_v1(root, season, decision_source, web_root=root / "web"))
    build("zone_profiles", lambda: build_zone_profiles(root, season))
    build("pitch_arsenal", lambda: build_pitch_arsenal(root, season))
    build("blocking", lambda: build_blocking(root, season))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--storage-root")
    parser.add_argument("--fixture")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--game-id")
    parser.add_argument("--rebuild-from-raw", action="store_true")
    parser.add_argument("--refresh-completed", action="store_true")
    parser.add_argument("--collection-mode", choices=("recent", "sample", "reconcile"), default="recent")
    parser.add_argument("--auto-reconcile", action="store_true")
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
            storage_root, args.season, args.refresh_naver, args.game_id,
            max(1, args.naver_workers), root
        )
        _exports(root, args.season, storage_root)
        print(f"rebuilt {games} games and {pitches} pitches")
        return
    if args.fixture:
        payload = json.loads(Path(args.fixture).read_text(encoding="utf-8-sig"))
        ok, message, pitches = process_payload(storage_root, payload, season=args.season, curated_root=root)
        if not ok:
            raise SystemExit(message)
        _exports(root, args.season, storage_root)
        print(f"processed {pitches} pitches")
        return

    client = VisualBaseballClient()
    store = Store(storage_root, root)
    schedule = client.get_json(f"/api/schedule/season?y={args.season}")["schedule"]
    mode = "reconcile" if args.refresh_completed else args.collection_mode
    target_games = select_target_games(schedule, store, args.season, mode, args.game_id)

    def fetch_game(game: dict, request_client: VisualBaseballClient) -> tuple[object, dict]:
        game_id = game["gameId"]
        payload = request_client.get_json(f"/api/game/pbp?id={game_id}", f"/game/{game_id}/pbp")
        innings = max((int(half.get("inning") or 0) for half in payload.get("pbpData", [])), default=9)
        naver_enrichment = _load_naver(store, args.season, game_id, innings, None, args.refresh_naver)
        if naver_enrichment is None:
            from .naver import NaverSportsClient
            naver_enrichment = _load_naver(
                store, args.season, game_id, innings, NaverSportsClient(), args.refresh_naver
            )
        # The retained payload is the canonical parse input; schedule data only selects targets.
        return prepare_game(payload, None, args.season, naver_enrichment), payload

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

    if mode == "sample" and fetched:
        changed_pitches = 0
        schema_or_y0_change = False
        for prepared, payload in fetched:
            manifest_path = source_manifest_path(root, args.season, prepared.game["game_id"])
            previous = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
            current_hash = pitch_sha256(
                prepared.game, prepared.events,
                [normalize_trajectory(row) for row in prepared.pitches],
            )
            changed_pitches += int(bool(previous) and previous.get("pitch_sha256") != current_hash)
            observed_y0 = sorted({float(row["y0"]) for row in prepared.pitches if row.get("y0") is not None})
            schema_or_y0_change |= bool(previous) and (
                previous.get("schema_sha256") != schema_sha256()
                or previous.get("observed_y0") != observed_y0
            )
        if schema_or_y0_change or changed_pitches >= 2:
            if args.auto_reconcile:
                sampled_ids = {game["gameId"] for game in target_games}
                remaining = [game for game in select_target_games(schedule, store, args.season, "reconcile", args.game_id)
                             if game["gameId"] not in sampled_ids]
                print(f"sample triggered automatic reconcile of {len(remaining)} games", flush=True)
                for index, game in enumerate(remaining, 1):
                    fetched.append(fetch_game(game, client))
                    if index % 25 == 0 or index == len(remaining):
                        print(f"Reconcile fetch: {index}/{len(remaining)} games", flush=True)
            else:
                print("WARNING: sample detected schema/y0 or multiple pitch-input changes; rerun with --auto-reconcile", flush=True)

    pending_games, pending_events, pending_pitches, pending_completions = [], [], [], []
    changed_games = 0

    def flush() -> None:
        nonlocal pending_games, pending_events, pending_pitches, pending_completions, changed_games
        changed_games += store.replace_games(pending_games, pending_events, pending_pitches)
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
    # Always plan exports: per-metric state handles data, code, and dependency no-ops.
    _exports(root, args.season, storage_root)
    print(f"reconciled {len(target_games)} games; {changed_games} curated shards changed")


if __name__ == "__main__":
    main()
