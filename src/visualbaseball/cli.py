from __future__ import annotations

import argparse, json
from pathlib import Path
from .collector import process_payload
from .export_excel import export_latest
from .http_client import VisualBaseballClient
from .parser import parse_game
from .storage import Store
from .validation import validate_game


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--root", default="."); parser.add_argument("--fixture"); parser.add_argument("--season", type=int, default=2026); parser.add_argument("--game-id")
    args = parser.parse_args(); root = Path(args.root).resolve()
    if args.fixture:
        payload = json.loads(Path(args.fixture).read_text(encoding="utf-8-sig")); ok, message, pitches = process_payload(root, payload, season=args.season)
        if not ok: raise SystemExit(message)
        export_latest(root); print(f"processed {pitches} pitches")
        return
    client, store = VisualBaseballClient(), Store(root); schedule = client.get_json(f"/api/schedule/season?y={args.season}")["schedule"]
    pending_games, pending_events, pending_pitches = [], [], []
    def flush() -> None:
        nonlocal pending_games, pending_events, pending_pitches
        store.replace_games(pending_games, pending_events, pending_pitches)
        pending_games, pending_events, pending_pitches = [], [], []
    for game_date, games in schedule.items():
        for game in games:
            if args.game_id and game.get("gameId") != args.game_id: continue
            status = str(game.get("status", ""))
            if status.lower() not in {"final", "finished", "end"} and (chr(0xC885) + chr(0xB8CC)) not in status: continue
            if not store.should_fetch(game["gameId"], game_date): continue
            payload = client.get_json(f"/api/game/pbp?id={game['gameId']}", f"/game/{game['gameId']}/pbp")
            parsed_game, events, pitches, _ = parse_game(payload, game, args.season)
            valid, message = validate_game(parsed_game, events, pitches)
            raw_path = store.write_raw(args.season, parsed_game["game_id"], payload)
            if valid and parsed_game["is_final"]:
                parsed_game["validation_status"] = "PASS"
                pending_games.append(parsed_game); pending_events.extend(events); pending_pitches.extend(pitches)
                store.mark(parsed_game["game_id"], "completed", raw_path, message)
                if len(pending_games) >= 25: flush()
            else:
                store.mark(parsed_game["game_id"], "failed" if parsed_game["is_final"] else "incomplete", raw_path, message)
    flush()
    export_latest(root)

if __name__ == "__main__": main()
