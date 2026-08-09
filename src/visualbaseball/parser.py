from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from .state_machine import GameState

PITCH_TYPE_CODES = {"\ud3ec\uc2ec": "FF", "\ud22c\uc2ec": "FT", "\uc2ac\ub77c\uc774\ub354": "SL", "\ucee4\ud130": "FC", "\uccb4\uc778\uc9c0\uc5c5": "CH", "\ucee4\ube0c": "CU", "\uc2f1\ucee4": "SI", "\ud3ec\ud06c": "FS", "\uc2a4\uc704\ud37c": "ST"}
PITCH_TYPE_NAMES = {"FF": "4-Seam Fastball", "FT": "2-Seam Fastball", "SL": "Slider", "FC": "Cutter", "CH": "Changeup", "CU": "Curveball", "SI": "Sinker", "FS": "Forkball", "ST": "Sweeper"}
KNOWN_PA_TYPES = {"bb", "hit", "k", "out", "hbp", "error", "fc", "sac", "hr"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _description(code: str, result: str) -> str:
    return {"B": "Ball", "F": "Foul", "S": "Swinging Strike", "T": "Called Strike", "X": result}.get((code or "").upper(), code or "")


def _state_fields(prefix: str, state: dict[str, Any]) -> dict[str, Any]:
    fields = {f"{name}_{prefix}": state[name] for name in ("balls", "strikes", "outs", "runner_1b_id", "runner_2b_id", "runner_3b_id", "base_state", "away_score", "home_score", "base_state_code", "re24_state_code", "re288_state_code")}
    return fields


def _official_half_score(away: dict[str, Any], home: dict[str, Any], inning: int, inning_half: str) -> tuple[int, int] | None:
    """Return the official cumulative score at the end of a half-inning.

    The API occasionally contradicts its `scoreAfter` snapshots while its
    `gameData.*.linescore` and PA records remain internally consistent.
    """
    away_line, home_line = away.get("linescore"), home.get("linescore")
    if not isinstance(away_line, list) or not isinstance(home_line, list) or len(away_line) < inning:
        return None
    if inning_half == "bottom" and len(home_line) < inning:
        return None
    def total(values: list[Any], count: int) -> int:
        return sum(int(value or 0) for value in values[:count])
    return total(away_line, inning), total(home_line, inning if inning_half == "bottom" else inning - 1)


def parse_game(payload: dict[str, Any], schedule_game: dict[str, Any] | None = None, season: int = 2026) -> tuple[dict, list[dict], list[dict], int]:
    schedule_game = schedule_game or {}
    game_data, halves = payload["gameData"], payload["pbpData"]
    game_id = str(game_data.get("gameId") or schedule_game.get("gameId"))
    away, home = game_data.get("away", {}), game_data.get("home", {})
    status = schedule_game.get("status") or game_data.get("status", "")
    fetched_at = _now()
    game = {"season": season, "game_date": f"{game_id[:4]}-{game_id[4:6]}-{game_id[6:8]}", "game_id": game_id,
            "away_team": schedule_game.get("away") or away.get("team", ""), "home_team": schedule_game.get("home") or home.get("team", ""),
            "stadium": schedule_game.get("stadium") or game_data.get("stadium", ""), "game_status": status,
            "away_score": int(schedule_game.get("aScore", away.get("score", -1))), "home_score": int(schedule_game.get("hScore", home.get("score", -1))),
            "is_final": (str(status).lower() in {"final", "finished", "end"} or (chr(0xC885) + chr(0xB8CC)) in str(status)), "fetched_at": fetched_at,
            "source_url": f"https://visualbaseball.com/api/game/pbp?id={game_id}", "source_hash": sha256(str(payload).encode()).hexdigest(), "validation_status": "PENDING"}
    state, events, pitches, unknown, event_seq, pa_counter, game_pitch = GameState(), [], [], 0, 0, 0, 0
    for half in halves:
        state.begin_half(int(half.get("inning", 0)), str(half.get("half", "")))
        for pa in half.get("pas") or []:
            pa_counter += 1; pa_id = f"{game_id}-{pa_counter:03d}"; state.balls = state.strikes = 0
            if state.outs >= 3:
                # Some source payloads append a duplicate PA after the third out.
                # Retain that limitation explicitly, but do not manufacture an
                # impossible pitch state with three outs before a pitch.
                snapshot = state.snapshot(); event_seq += 1
                events.append(_event(game, event_seq, pa_id, "state_adjustment", "SOURCE_POST_THIRD_OUT", "Source included a plate appearance after three outs; its pitches were not represented.", pa, snapshot, snapshot, 0, "unknown"))
                unknown += 1
                continue
            bases_before, bases_after = pa.get("basesBefore") or {}, pa.get("basesAfter") or {}
            before_snapshot = GameState(); before_snapshot.set_bases(bases_before)
            if state.base_state_code != before_snapshot.base_state_code or any(getattr(state, x) != getattr(before_snapshot, x) for x in ("runner_1b_id", "runner_2b_id", "runner_3b_id")):
                event_seq += 1; before, state_before = state.snapshot(), deepcopy(state.snapshot()); state.set_bases(bases_before); after = state.snapshot()
                events.append(_event(game, event_seq, pa_id, "state_adjustment", "SOURCE_SNAPSHOT", "Source base snapshot changed; underlying non-pitch event was not exposed.", pa, before, after, 0, "unknown")); unknown += 1
            for sub in pa.get("subs") or []:
                event_seq += 1; snapshot = state.snapshot()
                events.append(_event(game, event_seq, pa_id, "substitution", sub.get("t", ""), f"{sub.get('fromName','')} -> {sub.get('toName','')} ({sub.get('pos','')})", pa, snapshot, snapshot, 0, "source_limited"))
            pa_status = "ok" if str(pa.get("type", "")).lower() in KNOWN_PA_TYPES else "unknown"; unknown += pa_status == "unknown"
            pitch_list, terminal_before = pa.get("pitches") or [], None
            for index, pitch in enumerate(pitch_list, 1):
                game_pitch += 1; before = state.snapshot(); runs = 0
                if index == len(pitch_list):
                    terminal_before = deepcopy(before); runs = state.infer_runs(bases_after, int(pa.get("outsAfter", state.outs))); state.set_bases(bases_after); state.outs = int(pa.get("outsAfter", state.outs));
                    if state.inning_half == "top": state.away_score += runs
                    else: state.home_score += runs
                    state.balls = state.strikes = 0
                else: state.apply_non_terminal_pitch(str(pitch.get("r", "")))
                after = state.snapshot(); event_seq += 1
                events.append(_event(game, event_seq, pa_id, "pitch", str(pitch.get("r", "")), _description(str(pitch.get("r", "")), str(pa.get("result", ""))), pa, before, after, runs, pa_status))
                pitches.append(_pitch(game, event_seq, pa_id, index, game_pitch, pa, pitch, before, after, runs, index == len(pitch_list), pa_status))
            if terminal_before is None:
                terminal_before = state.snapshot(); runs = state.infer_runs(bases_after, int(pa.get("outsAfter", state.outs))); state.set_bases(bases_after); state.outs = int(pa.get("outsAfter", state.outs));
                if state.inning_half == "top": state.away_score += runs
                else: state.home_score += runs
                state.balls = state.strikes = 0
            after = state.snapshot(); event_seq += 1
            events.append(_event(game, event_seq, pa_id, "plate_appearance_result", str(pa.get("type", "")), str(pa.get("result", "")), pa, after if pitch_list else terminal_before, after, 0 if pitch_list else runs, "informational" if pitch_list and pa_status == "ok" else pa_status))
        score_after = half.get("scoreAfter")
        snapshot_score = (int(score_after[0]), int(score_after[1])) if isinstance(score_after, list) and len(score_after) >= 2 else None
        official_score = _official_half_score(away, home, state.inning, state.inning_half)
        target_score = official_score or snapshot_score
        if official_score and snapshot_score and official_score != snapshot_score:
            snapshot = state.snapshot(); event_seq += 1
            events.append(_event(game, event_seq, pa_id if 'pa_id' in locals() else "", "source_score_conflict", "SOURCE_SCORE_CONFLICT", f"Half-inning score snapshot {snapshot_score[0]}-{snapshot_score[1]} conflicts with official linescore {official_score[0]}-{official_score[1]}.", {}, snapshot, snapshot, 0, "unknown")); unknown += 1
        if target_score and (state.away_score, state.home_score) != target_score:
            before = state.snapshot(); state.away_score, state.home_score = target_score; after = state.snapshot(); event_seq += 1
            code = "OFFICIAL_LINESCORE_RECONCILIATION" if official_score else "SOURCE_SCORE_SNAPSHOT"
            description = "Score reconciled to official gameData linescore." if official_score else "Score synchronized to source half-inning snapshot."
            events.append(_event(game, event_seq, pa_id if 'pa_id' in locals() else "", "state_adjustment", code, description, {}, before, after, max(0, after["away_score"] - before["away_score"] + after["home_score"] - before["home_score"]), "source_limited" if official_score else "unknown")); unknown += 1
    return game, events, pitches, unknown


def _event(game, seq, pa_id, event_type, code, description, pa, before, after, runs, status):
    return {"game_id": game["game_id"], "stadium": game["stadium"], "event_seq": seq, "inning": before["inning"], "inning_half": before["inning_half"], "pa_id": pa_id, "event_type": event_type, "event_code": str(code), "description": description, "batter_id": str(pa.get("batterId", "")), "batter_name": pa.get("batter", ""), "pitcher_id": str(pa.get("pitcherId", "")), "pitcher_name": pa.get("pitcher", ""), "outs_before": before["outs"], "outs_after": after["outs"], "base_state_before": before["base_state"], "base_state_after": after["base_state"], "runs_on_event": runs, "away_score_before": before["away_score"], "home_score_before": before["home_score"], "away_score_after": after["away_score"], "home_score_after": after["home_score"], "parse_status": status}


def _pitch(game, event_seq, pa_id, number, game_number, pa, pitch, before, after, runs, terminal, status):
    stuff = str(pitch.get("stuff", "")); code = str(pitch.get("r", "")); pitch_type_code = PITCH_TYPE_CODES.get(stuff, "UN")
    row = {"season": game["season"], "game_date": game["game_date"], "game_id": game["game_id"], "stadium": game["stadium"], "event_seq": event_seq, "pa_id": pa_id, "pitch_id": f"{game['game_id']}-{pa_id}-{number:02d}", "pitch_number": number, "game_pitch_number": game_number, "inning": before["inning"], "inning_half": before["inning_half"], "batter_id": str(pa.get("batterId", "")), "batter_name": pa.get("batter", ""), "pitcher_id": str(pa.get("pitcherId", "")), "pitcher_name": pa.get("pitcher", ""), "pitch_type": PITCH_TYPE_NAMES.get(pitch_type_code, stuff), "pitch_type_code": pitch_type_code, "pitch_type_kr": stuff, "velocity_kmh": pitch.get("spd"), "velocity_mph": round(float(pitch.get("spd", 0)) * .621371, 1), "px": pitch.get("px"), "pz": pitch.get("pz"), "pitch_call_code": code, "pitch_result": _description(code, str(pa.get("result", ""))), "pa_result": pa.get("result", ""), "pa_type": pa.get("type", ""), "description": _description(code, str(pa.get("result", ""))), "is_swing": code in {"S", "F", "X"}, "is_take": code in {"B", "T"} or (terminal and str(pa.get("type", "")).lower() == "hbp"), "is_contact": code in {"F", "X"}, "is_in_play": code == "X", "is_pa_terminal": terminal, "runs_on_pitch": runs, "parse_status": status, "fetched_at": game["fetched_at"], "source_url": game["source_url"]}
    row.update(_state_fields("before", before)); row.update(_state_fields("after", after))
    for key in ("szTop", "szBot", "relH", "time", "vMov", "hMov", "dropAngle", "x0", "z0", "vx0", "vy0", "vz0", "ax", "ay", "az"):
        row[{"szTop":"sz_top","szBot":"sz_bottom","relH":"release_height_cm","time":"arrival_time_s","vMov":"vertical_movement_cm","hMov":"horizontal_movement_cm","dropAngle":"drop_angle"}.get(key, key)] = pitch.get(key)
    return row
