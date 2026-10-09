"""Cache 2025–2026 regular-season Naver inning relays, at most one request per second.

Run with PYTHONPATH=src: python analysis/sbj_location/bunt_relay_fetch.py [seasons...]   (default 2025 2026)
Interrupted runs resume from validated, ignored JSON files. Failures are logged
beside the raw files and never silently counted as complete.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import time

import requests

from naver_relay_location_fetch import DEST, ROOT

sys.path.insert(0, str(ROOT / "src"))
from visualbaseball.curated import load_rows


SEASONS = (2025, 2026)


def seasons_from_argv() -> tuple[int, ...]:
    return tuple(int(s) for s in sys.argv[1:]) or SEASONS


def games(seasons: tuple[int, ...] = SEASONS) -> list[str]:
    return sorted({str(row["game_id"]) for season in seasons
                   for row in load_rows(ROOT, "games", season, columns=["game_id", "is_final"])
                   if row["is_final"]})


def relay_at(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_bytes().decode("utf-8-sig"))
        return payload["result"]["textRelayData"] if payload.get("code") == 200 else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def final_inning(relay: dict) -> int:
    scores = relay.get("inningScore") or {}
    innings = [int(n) for side in scores.values() for n in side if str(n).isdigit()]
    if not innings:
        raise ValueError("inningScore has no innings")
    return max(innings)


def main() -> None:
    session = requests.Session()
    session.headers.update({"User-Agent": "visualbaseball-savant-collector/1.0"})
    last_request = 0.0
    log_path = DEST / "bunt_fetch_log.jsonl"
    DEST.mkdir(parents=True, exist_ok=True)
    targets = games(seasons_from_argv())
    failures = 0
    print(f"games={len(targets)}", flush=True)
    with log_path.open("a", encoding="utf-8") as log:
        for game_index, game_id in enumerate(targets, 1):
            season = game_id[:4]
            folder = DEST / season / game_id
            folder.mkdir(parents=True, exist_ok=True)
            inning, last_inning = 1, None
            while last_inning is None or inning <= last_inning:
                path = folder / f"inning_{inning}.json"
                relay = relay_at(path)
                status, error = "cached", ""
                if relay is None:
                    url = f"https://api-gw.sports.naver.com/schedule/games/{game_id}{season}/relay?inning={inning}"
                    for _ in range(4):
                        time.sleep(max(0, 1.05 - (time.monotonic() - last_request)))
                        last_request = time.monotonic()
                        try:
                            response = session.get(url, timeout=30)
                            response.raise_for_status()
                            payload = json.loads(response.content.decode("utf-8-sig"))
                            relay = payload["result"]["textRelayData"] if payload.get("code") == 200 else None
                            if relay is None:
                                raise ValueError("invalid relay payload")
                            if inning == 1:
                                final_inning(relay)
                            path.write_bytes(response.content)
                            status = "fetched"
                            break
                        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                            relay = None
                            error = f"{type(exc).__name__}: {exc}"
                    if relay is None:
                        status = "failed"
                if relay is not None and last_inning is None:
                    try:
                        last_inning = final_inning(relay)
                    except ValueError as exc:
                        status, error = "failed", str(exc)
                log.write(json.dumps({"game_id": game_id, "inning": inning, "status": status,
                                      "error": error}, ensure_ascii=False) + "\n")
                log.flush()
                if status == "failed":
                    failures += 1
                    print(f"FAILED {game_id} inning={inning} {error}", flush=True)
                    break
                inning += 1
            if game_index % 20 == 0 or game_index == len(targets):
                print(f"games={game_index}/{len(targets)} last={game_id}", flush=True)
    if failures:
        raise SystemExit(f"{failures} games have failed innings; rerun to retry them")


if __name__ == "__main__":
    main()
