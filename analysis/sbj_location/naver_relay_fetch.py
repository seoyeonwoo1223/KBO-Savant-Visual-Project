"""Fill the Naver relay cache for a game list (resume-safe; read-only apart from the gitignored cache).

    PYTHONPATH=src python analysis/sbj_location/naver_relay_fetch.py GAMES_JSON [FAILED_JSON]

GAMES_JSON is {"<season>": [game_id, ...]} (e.g. results/naver_count_audit_games_2019_2026.json). Relays are cached
unmodified under data/raw/naver/relay_raw/<season>/<game_id>/inning_N.json (gitignored); a cached inning is never
requested again, so an interrupted run can simply be restarted. Request starts are kept >= 1.05 s apart by one
shared limiter; three workers only overlap the time spent waiting for responses. Games with a missing inning are
written to FAILED_JSON (default: stdout summary only).
"""
from __future__ import annotations

import json, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

import requests

from naver_queue_verify import DEST, final_inning

_lock, _next, _local = threading.Lock(), [0.0], threading.local()


def _slot() -> None:
    with _lock:
        now = time.monotonic(); wait = max(0.0, _next[0] - now); _next[0] = max(now, _next[0]) + 1.05
    time.sleep(wait)


def _ok(payload: dict) -> bool:
    return payload.get("code") == 200 and bool((payload.get("result") or {}).get("textRelayData"))


def get(game_id: str, inning: int) -> dict | None:
    path = DEST / game_id[:4] / game_id / f"inning_{inning}.json"
    if path.exists():
        try:
            payload = json.loads(path.read_bytes().decode("utf-8-sig"))
            if _ok(payload):
                return payload["result"]["textRelayData"]
        except ValueError:
            pass
    if not hasattr(_local, "session"):
        _local.session = requests.Session(); _local.session.headers.update({"User-Agent": "visualbaseball-savant-collector/1.0"})
    for _ in range(3):
        _slot()
        try:
            r = _local.session.get(f"https://api-gw.sports.naver.com/schedule/games/{game_id}{game_id[:4]}/relay?inning={inning}", timeout=30)
            r.raise_for_status(); payload = json.loads(r.content.decode("utf-8-sig"))
            if _ok(payload):
                path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(r.content)
                return payload["result"]["textRelayData"]
        except (requests.RequestException, ValueError):
            pass
    return None


def fetch_game(game_id: str) -> tuple[str, list[int]]:
    first = get(game_id, 1)
    if first is None:
        return game_id, [1]
    return game_id, [i for i in range(2, final_inning(first) + 1) if get(game_id, i) is None]


def main() -> None:
    data = json.loads(open(sys.argv[1], encoding="utf-8").read())
    games = [g for gs in data.get("games", data).values() for g in gs]
    failed = {}
    with ThreadPoolExecutor(3) as pool:
        for i, (game_id, missing) in enumerate(pool.map(fetch_game, games), 1):
            if missing:
                failed[game_id] = missing
            if i % 50 == 0:
                print(i, "/", len(games), game_id, flush=True)
    if len(sys.argv) > 2:
        open(sys.argv[2], "w", encoding="utf-8").write(json.dumps(failed, indent=1))
    print("done", len(games), "games; incomplete", len(failed), flush=True)


if __name__ == "__main__":
    main()
