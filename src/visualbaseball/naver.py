"""Small, normalized bridge to the public Naver Sports game relay.

The relay endpoint returns one inning at a time. We retain only the fields
needed to join pitches and non-pitch runner events to the Visual Baseball
curated layer rather than copying the full relay commentary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
import time
from typing import Any

import requests


NAVER_SCHEMA_VERSION = 2
WP_RE = re.compile(r"폭투|와일드\s*피치")
PB_RE = re.compile(r"포일|패스\s*볼|패스트\s*볼")
PICKOFF_RE = re.compile(r"견제")
BASE_RE = re.compile(r"([123])루")
RUNNER_RE = re.compile(r"([123])루\s*주자\s+([^:]+)")
PICKOFF_OUT_RE = re.compile(r"견제(?:사|아웃)|견제[^\n]*아웃|견제로\s*아웃")
PICKOFF_ERROR_RE = re.compile(r"견제[^\n]*(?:실책|악송구)")


def pitch_key(inning: int, inning_half: str, batter_id: str, pitcher_id: str, pitch_number: int) -> tuple[int, str, str, str, int]:
    return (int(inning), inning_half, str(batter_id), str(pitcher_id), int(pitch_number))


@dataclass
class NaverEnrichment:
    """Pitch flags, catchers and pickoff attempts derived from a complete relay."""

    game_id: str
    source_game_id: str
    source_urls: list[str]
    pitch_events: dict[tuple[int, str, str, str, int], list[dict[str, Any]]]
    starters: dict[str, dict[str, str]]
    pickoff_events: list[dict[str, Any]] = field(default_factory=list)
    coverage: str = "relay"
    schema_version: int = NAVER_SCHEMA_VERSION

    @property
    def has_pickoff_coverage(self) -> bool:
        return self.schema_version >= NAVER_SCHEMA_VERSION and self.coverage == "relay"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "game_id": self.game_id,
            "source_game_id": self.source_game_id,
            "source_urls": self.source_urls,
            "starters": self.starters,
            "coverage": self.coverage,
            "pickoff_events": self.pickoff_events,
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
        return cls(
            str(value.get("game_id", "")),
            str(value.get("source_game_id", "")),
            list(value.get("source_urls", [])),
            events,
            dict(value.get("starters", {})),
            list(value.get("pickoff_events", [])),
            str(value.get("coverage", "relay")),
            int(value.get("schema_version") or 1),
        )


def _starter(lineup: dict[str, Any]) -> dict[str, str] | None:
    catchers = [player for player in lineup.get("batter", []) if int(player.get("pos", -1)) == 2]
    if not catchers:
        return None
    player = min(catchers, key=lambda item: int(item.get("seqno") or 999))
    return {"id": str(player.get("pcode", "")), "name": str(player.get("name", "")), "source": "naver_lineup"}


def _pickoff_event(option: dict[str, Any], inning: int, inning_half: str,
                   pa_index: int, option_index: int) -> dict[str, Any] | None:
    text = str(option.get("text", "")).strip()
    if not PICKOFF_RE.search(text):
        return None
    state = option.get("currentGameState") or {}
    base_match = BASE_RE.search(text)
    runner_match = RUNNER_RE.search(text)
    raw_seq = option.get("seqno")
    source_seq = str(raw_seq) if raw_seq not in (None, "") else f"{pa_index}:{option_index}"
    pitch_number = option.get("pitchNum")
    try:
        pitch_number = int(pitch_number or 0)
    except (TypeError, ValueError):
        pitch_number = 0
    return {
        "inning": int(inning),
        "inning_half": inning_half,
        "source_seq": source_seq,
        "pitch_number_context": pitch_number,
        "batter_id": str(state.get("batter", "")),
        "pitcher_id": str(state.get("pitcher", "")),
        "pickoff_base": int(base_match.group(1)) if base_match else None,
        "runner_name": runner_match.group(2).strip() if runner_match else "",
        "is_pickoff_out": bool(PICKOFF_OUT_RE.search(text)),
        "is_pickoff_error": bool(PICKOFF_ERROR_RE.search(text)),
        "text": text,
    }


def build_enrichment(game_id: str, relay_payloads: list[dict[str, Any]], source_urls: list[str] | None = None) -> NaverEnrichment:
    """Turn complete inning relays into normalized pitch and pickoff events.

    In the relay text, a wild-pitch/passed-ball advance is emitted immediately
    after the pitch it belongs to, so it is attached to the latest pitch.
    Pickoffs remain independent non-pitch events because multiple attempts may
    occur between consecutive pitches.
    """
    pitch_events: dict[tuple[int, str, str, str, int], list[dict[str, Any]]] = {}
    pickoff_events: list[dict[str, Any]] = []
    starters: dict[str, dict[str, str]] = {}
    seen_pickoffs: set[tuple[int, str, str, str]] = set()
    source_game_id = ""
    for payload in relay_payloads:
        relay = (payload.get("result") or {}).get("textRelayData") or {}
        source_game_id = source_game_id or str(relay.get("gameId", ""))
        for side, field_name in (("home", "homeLineup"), ("away", "awayLineup")):
            if side not in starters:
                catcher = _starter(relay.get(field_name) or {})
                if catcher:
                    starters[side] = catcher
        plate_appearances = sorted(
            relay.get("textRelays") or [],
            key=lambda item: min((int(option.get("seqno") or 0) for option in item.get("textOptions") or []), default=0),
        )
        for pa_index, plate_appearance in enumerate(plate_appearances, 1):
            inning = int(plate_appearance.get("inn") or 0)
            inning_half = "top" if str(plate_appearance.get("homeOrAway")) == "0" else "bottom"
            last_pitch: dict[str, Any] | None = None
            for option_index, option in enumerate(plate_appearance.get("textOptions") or [], 1):
                text = str(option.get("text", ""))
                if last_pitch is not None:
                    last_pitch["is_wild_pitch"] = last_pitch["is_wild_pitch"] or bool(WP_RE.search(text))
                    last_pitch["is_passed_ball"] = last_pitch["is_passed_ball"] or bool(PB_RE.search(text))
                pickoff = _pickoff_event(option, inning, inning_half, pa_index, option_index)
                if pickoff is not None:
                    identity = (inning, inning_half, pickoff["source_seq"], pickoff["text"])
                    if identity not in seen_pickoffs:
                        seen_pickoffs.add(identity)
                        pickoff_events.append(pickoff)
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
    return NaverEnrichment(
        game_id, source_game_id, source_urls or [], pitch_events, starters,
        pickoff_events=pickoff_events, coverage="relay", schema_version=NAVER_SCHEMA_VERSION,
    )


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
        """Fetch every inning relay so pickoff attempts have complete game coverage."""
        naver_game_id = f"{game_id}{season}"
        payloads: list[dict[str, Any]] = []
        urls: list[str] = []
        for inning in range(1, innings + 1):
            path = f"/schedule/games/{naver_game_id}/relay?inning={inning}"
            payloads.append(self.get_json(path))
            urls.append(f"{self.base_url}{path}")
            time.sleep(0.15)
        enrichment = build_enrichment(game_id, payloads, urls)
        if not enrichment.source_game_id:
            enrichment.source_game_id = naver_game_id
        return enrichment
