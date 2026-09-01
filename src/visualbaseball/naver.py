"""Small, normalized bridge to the public Naver Sports game relay.

The relay endpoint returns one inning at a time.  We deliberately retain only
the fields needed to join it to a Visual Baseball pitch, rather than copying
relay commentary into the repository.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
import time
from typing import Any

import requests


WP_RE = re.compile(r"폭투|와일드\s*피치")
PB_RE = re.compile(r"포일|패스\s*볼|패스트\s*볼")


def pitch_key(inning: int, inning_half: str, batter_id: str, pitcher_id: str, pitch_number: int) -> tuple[int, str, str, str, int]:
    return (int(inning), inning_half, str(batter_id), str(pitcher_id), int(pitch_number))


@dataclass
class NaverEnrichment:
    """Pitch-level flags and starting catchers derived from a complete relay."""

    game_id: str
    source_game_id: str
    source_urls: list[str]
    pitch_events: dict[tuple[int, str, str, str, int], list[dict[str, Any]]]
    starters: dict[str, dict[str, str]]
    coverage: str = "relay"

    def to_dict(self) -> dict[str, Any]:
        return {
            "game_id": self.game_id,
            "source_game_id": self.source_game_id,
            "source_urls": self.source_urls,
            "starters": self.starters,
            "coverage": self.coverage,
            "pitch_events": [
                {"inning": key[0], "inning_half": key[1], "batter_id": key[2], "pitcher_id": key[3], "pitch_number": key[4], **value}
                for key, values in sorted(self.pitch_events.items()) for value in values
            ],
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "NaverEnrichment":
        events: dict[tuple[int, str, str, str, int], list[dict[str, Any]]] = {}
        for event in value.get("pitch_events", []):
            key = pitch_key(event["inning"], event["inning_half"], event["batter_id"], event["pitcher_id"], event["pitch_number"])
            events.setdefault(key, []).append({
                name: event.get(name) for name in ("naver_pitch_id", "is_wild_pitch", "is_passed_ball")
            })
        return cls(str(value.get("game_id", "")), str(value.get("source_game_id", "")), list(value.get("source_urls", [])), events, dict(value.get("starters", {})), str(value.get("coverage", "relay")))


def _starter(lineup: dict[str, Any]) -> dict[str, str] | None:
    catchers = [player for player in lineup.get("batter", []) if int(player.get("pos", -1)) == 2]
    if not catchers:
        return None
    player = min(catchers, key=lambda item: int(item.get("seqno") or 999))
    return {"id": str(player.get("pcode", "")), "name": str(player.get("name", "")), "source": "naver_lineup"}


def build_enrichment(game_id: str, relay_payloads: list[dict[str, Any]], source_urls: list[str] | None = None) -> NaverEnrichment:
    """Turn inning relay payloads into a lossless-enough pitch join index.

    In the relay text, a wild-pitch/passed-ball advance is emitted immediately
    *before* the pitch text it belongs to.  Multiple runner advances therefore
    collapse to one flag on that next pitch.
    """
    pitch_events: dict[tuple[int, str, str, str, int], list[dict[str, Any]]] = {}
    starters: dict[str, dict[str, str]] = {}
    source_game_id = ""
    for payload in relay_payloads:
        relay = (payload.get("result") or {}).get("textRelayData") or {}
        source_game_id = source_game_id or str(relay.get("gameId", ""))
        for side, field in (("home", "homeLineup"), ("away", "awayLineup")):
            if side not in starters:
                catcher = _starter(relay.get(field) or {})
                if catcher:
                    starters[side] = catcher
        plate_appearances = sorted(relay.get("textRelays") or [], key=lambda item: min((int(option.get("seqno") or 0) for option in item.get("textOptions") or []), default=0))
        for plate_appearance in plate_appearances:
            inning = int(plate_appearance.get("inn") or 0)
            inning_half = "top" if str(plate_appearance.get("homeOrAway")) == "0" else "bottom"
            last_pitch: dict[str, Any] | None = None
            for option in plate_appearance.get("textOptions") or []:
                text = str(option.get("text", ""))
                if last_pitch is not None:
                    last_pitch["is_wild_pitch"] = last_pitch["is_wild_pitch"] or bool(WP_RE.search(text))
                    last_pitch["is_passed_ball"] = last_pitch["is_passed_ball"] or bool(PB_RE.search(text))
                if not option.get("ptsPitchId"):
                    continue
                state = option.get("currentGameState") or {}
                key = pitch_key(inning, inning_half, state.get("batter", ""), state.get("pitcher", ""), option.get("pitchNum") or 0)
                last_pitch = {
                    "naver_pitch_id": str(option.get("ptsPitchId")),
                    "is_wild_pitch": False,
                    "is_passed_ball": False,
                }
                pitch_events.setdefault(key, []).append(last_pitch)
    return NaverEnrichment(game_id, source_game_id, source_urls or [], pitch_events, starters)


class NaverSportsClient:
    """Public, unauthenticated Naver Sports relay client with modest retries."""

    base_url = "https://api-gw.sports.naver.com"

    def __init__(self, timeout: int = 30):
        self.timeout, self.session = timeout, requests.Session()
        self.session.headers.update({"User-Agent": "visualbaseball-savant-collector/1.0"})

    def get_json(self, path: str) -> dict[str, Any]:
        error: Exception | None = None
        for attempt in range(3):
            try:
                response = self.session.get(f"{self.base_url}{path}", timeout=self.timeout)
                if response.status_code == 429 or response.status_code >= 500:
                    raise requests.HTTPError(f"transient HTTP {response.status_code}", response=response)
                response.raise_for_status()
                return json.loads(response.content.decode("utf-8-sig"))
            except (requests.RequestException, json.JSONDecodeError) as caught:
                error = caught
                if attempt < 2:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"Naver GET failed after retries: {path}: {error}") from error

    def fetch_enrichment(self, game_id: str, season: int, innings: int) -> NaverEnrichment:
        naver_game_id = f"{game_id}{season}"
        record_path = f"/schedule/games/{naver_game_id}/record"
        record = self.get_json(record_path)
        record_data = (record.get("result") or {}).get("recordData") or {}
        event_labels = [str(item.get("how", "")) for item in record_data.get("etcRecords") or []]
        record_url = f"{self.base_url}{record_path}"
        if not any(WP_RE.search(label) or PB_RE.search(label) for label in event_labels):
            return NaverEnrichment(game_id, naver_game_id, [record_url], {}, {}, "record_no_event")
        payloads, urls = [], [record_url]
        for inning in range(1, innings + 1):
            path = f"/schedule/games/{naver_game_id}/relay?inning={inning}"
            payloads.append(self.get_json(path)); urls.append(f"{self.base_url}{path}")
            time.sleep(0.15)
        return build_enrichment(game_id, payloads, urls)
