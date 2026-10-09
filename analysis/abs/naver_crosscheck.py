"""ABS 재구성 불일치 투구를 네이버 스포츠 문자중계 PTS 기록과 대조한다 (읽기 전용, 연구용).

입력: data/experimental/abs/reconstruction_mismatches.csv (python -m visualbaseball.abs_explorer 산출물)
대조: 네이버 relay의 textOptions(pitchResult 판정·문자)와 ptsOptions(궤적 계수·topSz/bottomSz)를
      VB curated naver_pitch_id(= ptsPitchId)로 짝지은 뒤, 같은 규정 기하로 판정을 다시 계산한다.
출력: data/experimental/abs/naver_crosscheck.csv, naver_crosscheck.json

    PYTHONPATH=src python analysis/abs/naver_crosscheck.py [--cache DIR]

네이버 PTS와 VB는 같은 PTS 계통일 가능성이 높다. 이 대조는 판정·좌표 "기록"이 두 공개 경로에서 같은지를
확인할 뿐, 측정 정확도를 검증하지 않는다.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from visualbaseball import abs_zone as az
from visualbaseball.curated import load_table
from visualbaseball.naver import NaverSportsClient
from visualbaseball.publish import write_json

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/experimental/abs"
TRAJECTORY = ("x0", "y0", "z0", "vx0", "vy0", "vz0", "ax", "ay", "az")
VB_COLUMNS = ["pitch_id", "game_id", "inning", "inning_half", "pitch_number", "naver_pitch_id", "pitcher_id", "batter_id", "pitch_call_code",
              "balls_before", "strikes_before", "px", "pz", "sz_top", "sz_bottom", *TRAJECTORY]
# 네이버 pitchResult: B 볼, T 루킹 스트라이크, S 헛스윙, F 파울, H 타격 등 (문자 text도 함께 저장)
TRAJECTORY_TOLERANCE = 1e-3


def relay(client: NaverSportsClient, cache: Path, game_id: str, season: int, inning: int) -> dict:
    path = cache / f"{game_id}_{inning}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    payload = client.get_json(f"/schedule/games/{game_id}{season}/relay?inning={inning}")
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    time.sleep(0.15)
    return payload


def naver_pitches(payload: dict) -> tuple[dict[str, dict], dict[tuple, list[str]]]:
    """ptsPitchId -> {call, text, pitch_num, trajectory, topSz, bottomSz, crossPlateX/Y}, and
    (pitcher, batter, pitchNum) -> ptsPitchIds for rows whose curated naver_pitch_id is empty."""
    data = ((payload.get("result") or {}).get("textRelayData") or {})
    out: dict[str, dict] = {}
    keys: dict[tuple, list[str]] = {}
    for block in data.get("textRelays") or []:
        for option in block.get("textOptions") or []:
            pid = option.get("ptsPitchId")
            if pid:
                state = option.get("currentGameState") or {}
                key = (str(state.get("pitcher", "")), str(state.get("batter", "")), int(option.get("pitchNum") or 0))
                keys.setdefault(key, []).append(str(pid))
                out.setdefault(str(pid), {}).update({"naver_call": option.get("pitchResult"), "naver_text": option.get("text"),
                                                     "naver_pitch_num": option.get("pitchNum")})
        for pts in block.get("ptsOptions") or []:
            pid = pts.get("pitchId")
            if pid:
                out.setdefault(str(pid), {}).update({f"naver_{k}": pts.get(k) for k in (*TRAJECTORY, "topSz", "bottomSz", "crossPlateX", "crossPlateY")})
    return out, keys


def margin(row: dict, prefix: str, season: int) -> float:
    traj = [np.array([float(row[f"{prefix}{k}"]) if row.get(f"{prefix}{k}") is not None else np.nan]) for k in TRAJECTORY]
    x_mid, z_mid = az.plane_position_cm(*traj, az.MID_PLANE_Y_FT)
    _, z_back = az.plane_position_cm(*traj, az.BACK_PLANE_Y_FT)
    top_key, bottom_key = ("naver_topSz", "naver_bottomSz") if prefix else ("sz_top", "sz_bottom")
    top, bottom = float(row[top_key]) * az.CM_PER_FOOT, float(row[bottom_key]) * az.CM_PER_FOOT
    value, _ = az.zone_margin_cm(az.zone_margins_cm(x_mid, z_mid, z_back, [top], [bottom], season))
    return float(value[0])


def classify(r: dict) -> str:
    if r.get("naver_call") is None:
        return "naver_unmatched"
    if r["naver_call"] not in ("B", "T"):
        return "naver_not_a_take"
    if not r["same_trajectory"]:
        return "trajectory_differs"
    if r["naver_call"] != r["pitch_call_code"]:
        # 네이버 판정이 재구성과 같고 VB 기록만 다르면 VB 판정 기록 오류 의심
        return "vb_call_record_differs"
    return "both_sources_agree_reconstruction_differs"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=Path("/tmp/naver_relay_cache"))
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    mismatches = pd.read_csv(OUT / "reconstruction_mismatches.csv", dtype={"pitch_id": str})
    rows = []
    client = NaverSportsClient()
    for season, part in mismatches.groupby("season"):
        vb = load_table(ROOT, "pitches", int(season), columns=VB_COLUMNS).to_pandas()
        vb = vb[vb["pitch_id"].isin(part["pitch_id"])]
        for record in part.merge(vb, on="pitch_id", how="left", suffixes=("", "_vb")).to_dict("records"):
            pitches, keys = naver_pitches(relay(client, args.cache, record["game_id"], int(season), int(record["inning"])))
            pid, record["match"] = str(record["naver_pitch_id"]), "naver_pitch_id"
            if pid not in pitches:
                # Same inning, pitcher, batter and pitch number; only an unambiguous single candidate counts.
                candidates = set(keys.get((str(record["pitcher_id"]), str(record["batter_id"]), int(record["pitch_number"])), []))
                pid, record["match"] = (candidates.pop(), "inning_pitcher_batter_pitchnum") if len(candidates) == 1 else ("", "none")
            found = pitches.get(pid, {})
            record["naver_pitch_id"] = pid or None
            record.update(found)
            record["same_trajectory"] = bool(found) and all(
                found.get(f"naver_{k}") is not None and abs(float(found[f"naver_{k}"]) - float(record[k])) <= TRAJECTORY_TOLERANCE for k in TRAJECTORY)
            record["same_zone"] = bool(found) and found.get("naver_topSz") is not None and \
                abs(float(found["naver_topSz"]) - float(record["sz_top"])) <= TRAJECTORY_TOLERANCE and \
                abs(float(found["naver_bottomSz"]) - float(record["sz_bottom"])) <= TRAJECTORY_TOLERANCE
            record["naver_margin_cm"] = margin(record, "naver_", int(season)) if found.get("naver_x0") is not None else None
            record["reconstructed_call"] = "T" if record["zone_margin_cm"] >= 0 else "B"
            record["category"] = classify(record)
            rows.append(record)
    table = pd.DataFrame(rows)
    keep = ["pitch_id", "season", "game_date", "stadium", "inning", "pitcher_name", "batter_name", "pitch_code", "balls_before",
            "strikes_before", "pitch_call_code", "reconstructed_call", "zone_margin_cm", "binding_edge", "far_from_boundary",
            "match", "naver_pitch_id", "naver_call", "naver_text", "same_trajectory", "same_zone", "naver_margin_cm", "category"]
    table = table[keep].sort_values(["far_from_boundary", "season", "game_date", "pitch_id"], ascending=[False, True, True, True])
    table.round(3).to_csv(OUT / "naver_crosscheck.csv", index=False)
    summary = {"schema_version": 1, "status": "experimental", "source": "api-gw.sports.naver.com relay textOptions/ptsOptions",
               "matched_by": "curated naver_pitch_id == Naver ptsPitchId, else a unique (inning, pitcher, batter, pitch number)",
               "match": {k: int(v) for k, v in Counter(table["match"]).items()},
               "all": {k: int(v) for k, v in Counter(table["category"]).items()},
               "far_from_boundary": {k: int(v) for k, v in Counter(table.loc[table["far_from_boundary"], "category"]).items()},
               "near_boundary": {k: int(v) for k, v in Counter(table.loc[~table["far_from_boundary"], "category"]).items()}}
    write_json(OUT / "naver_crosscheck.json", summary, compact=False)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
