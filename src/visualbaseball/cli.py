from __future__ import annotations

import argparse, json
from pathlib import Path
from .collector import cache_payload, prepare_game, process_payload, rebuild_from_raw
from .export_excel import export_latest
from .web_export import export_web_data
from .http_client import VisualBaseballClient
from .storage import Store
from .swing_take import build_swing_take


def _exports(root: Path, season: int, storage_root: Path) -> None:
    build_swing_take(storage_root, season)
    export_latest(root, season, storage_root)
    if storage_root == root:
        export_web_data(root)


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--root", default="."); parser.add_argument("--storage-root"); parser.add_argument("--fixture"); parser.add_argument("--season", type=int, default=2026); parser.add_argument("--game-id"); parser.add_argument("--rebuild-from-raw", action="store_true")
    args = parser.parse_args(); root = Path(args.root).resolve(); storage_root = Path(args.storage_root).resolve() if args.storage_root else root
    if args.rebuild_from_raw:
        games, pitches = rebuild_from_raw(storage_root, args.season)
        _exports(root, args.season, storage_root)
        print(f"rebuilt {games} games and {pitches} pitches")
        return
    if args.fixture:
        payload = json.loads(Path(args.fixture).read_text(encoding="utf-8-sig")); ok, message, pitches = process_payload(storage_root, payload, season=args.season)
        if not ok: raise SystemExit(message)
        _exports(root, args.season, storage_root)
        print(f"processed {pitches} pitches")
        return
    client, store = VisualBaseballClient(), Store(storage_root); schedule = client.get_json(f"/api/schedule/season?y={args.season}")["schedule"]
    pending_games, pending_events, pending_pitches, pending_completions = [], [], [], []
    def flush() -> None:
        nonlocal pending_games, pending_events, pending_pitches, pending_completions
        store.replace_games(pending_games, pending_events, pending_pitches)
        for prepared, raw_path in pending_completions:
            store.mark(prepared.game["game_id"], "completed", raw_path, prepared.message)
        pending_games, pending_events, pending_pitches, pending_completions = [], [], [], []
    for game_date, games in schedule.items():
        for game in games:
            if args.game_id and game.get("gameId") != args.game_id: continue
            status = str(game.get("status", ""))
            if status.lower() not in {"final", "finished", "end"} and (chr(0xC885) + chr(0xB8CC)) not in status: continue
            if not store.should_fetch(game["gameId"], game_date): continue
            payload = client.get_json(f"/api/game/pbp?id={game['gameId']}", f"/game/{game['gameId']}/pbp")
            prepared = prepare_game(payload, game, args.season)
            raw_path = cache_payload(store, args.season, payload, prepared)
            if raw_path:
                pending_games.append(prepared.game); pending_events.extend(prepared.events); pending_pitches.extend(prepared.pitches)
                pending_completions.append((prepared, raw_path))
                if len(pending_games) >= 25: flush()
    flush()
    _exports(root, args.season, storage_root)


if __name__ == "__main__": main()
