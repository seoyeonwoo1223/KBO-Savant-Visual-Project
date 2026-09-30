"""Fetch the ten investigated games' complete, unmodified Naver inning relays.

Run from any directory: python analysis/sbj_location/naver_relay_location_fetch.py
The JSON is ignored by Git. A compact fetch log beside the JSON records failures.
"""
from __future__ import annotations

import json
from pathlib import Path
import time

import requests

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / "data/raw/naver/relay_raw"
GAMES = (
    "20250809OBWO0", "20240724WOOB0", "20240404LTHH0", "20240504OBLG0",
    "20260509KTWO0", "20250614HTNC0", "20210606HHNC0", "20210512SSKT0",
    "20210828NCHH0", "20200630LTNC0",
)


def fetch_all() -> None:
    session = requests.Session()
    session.headers.update({"User-Agent": "visualbaseball-savant-collector/1.0"})
    last_request = 0.0
    log = []
    for game_id in GAMES:
        season = game_id[:4]
        folder = DEST / season / game_id
        folder.mkdir(parents=True, exist_ok=True)
        inning = 1
        final_inning = None
        while final_inning is None or inning <= final_inning:
            path = folder / f"inning_{inning}.json"
            if path.exists():
                try:
                    payload = json.loads(path.read_bytes().decode("utf-8-sig"))
                    status = "cached"
                except (ValueError, UnicodeDecodeError):
                    payload = None
            else:
                payload = None
            if payload is None:
                url = f"https://api-gw.sports.naver.com/schedule/games/{game_id}{season}/relay?inning={inning}"
                error = ""
                for attempt in range(4):  # initial request plus at most three retries
                    time.sleep(max(0, 1.05 - (time.monotonic() - last_request)))
                    last_request = time.monotonic()
                    try:
                        response = session.get(url, timeout=30)
                        response.raise_for_status()
                        payload = json.loads(response.content.decode("utf-8-sig"))
                        if payload.get("code") != 200 or not (payload.get("result") or {}).get("textRelayData"):
                            raise ValueError(f"invalid relay response: code={payload.get('code')}")
                        path.write_bytes(response.content)
                        status = "fetched"
                        break
                    except (requests.RequestException, ValueError) as exc:
                        error = f"{type(exc).__name__}: {exc}"
                if payload is None or not path.exists():
                    log.append({"game_id": game_id, "inning": inning, "status": "failed", "error": error})
                    print(game_id, inning, "failed", error, flush=True)
                    break
            relay = payload["result"]["textRelayData"]
            if final_inning is None:
                score = relay.get("inningScore") or {}
                final_inning = max(int(n) for side in score.values() for n in side if str(n).isdigit())
            log.append({"game_id": game_id, "inning": inning, "status": status})
            print(game_id, inning, status, flush=True)
            inning += 1
    DEST.mkdir(parents=True, exist_ok=True)
    (DEST / "fetch_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    fetch_all()
