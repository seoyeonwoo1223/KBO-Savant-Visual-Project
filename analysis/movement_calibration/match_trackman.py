"""VB 투구와 TrackMan 투구를 투구 단위로 짝짓는다 (무브먼트 보정 연구용, 저장소 데이터는 바꾸지 않음).

규칙: scripts/build_trackman_id_crosswalk.py의 경기 매핑과 순서 정렬(반이닝 안 타석 순서,
타석 안 투구 번호)을 그대로 쓰고, 투구 전 볼·스트라이크·아웃 일치, 대응표로 조회한 투수·타자
ID 일치, 구속 차 허용 범위(--speed-tolerance, km/h)를 모두 통과한 투구만 남긴다.

    PYTHONPATH=src python analysis/movement_calibration/match_trackman.py --out /tmp/mc
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

from visualbaseball.curated import load_rows

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("crosswalk", ROOT / "scripts" / "build_trackman_id_crosswalk.py")
crosswalk = importlib.util.module_from_spec(spec); spec.loader.exec_module(crosswalk)

VB_COLUMNS = ["pitch_id", "game_id", "inning", "inning_half", "pitcher_id", "pitcher_name", "batter_id", "batter_name",
              "balls_before", "strikes_before", "outs_before", "stadium", "pitch_type", "pitch_type_code", "pitch_type_kr",
              "velocity_kmh", "horizontal_movement_cm", "vertical_movement_cm", "px", "pz", "sz_top", "sz_bottom",
              "release_height_cm", "release_x_50", "release_x_55", "release_z_55", "trajectory_valid", "arrival_time_s",
              "x0", "y0", "z0", "vx0", "vy0", "vz0", "ax", "ay", "az", "pitch_call_code", "batter_stance"]
TM_COLUMNS = ["pitcher_hand", "batter_hand", "tagged_pitch_type", "auto_pitch_type", "pitch_type_group", "rel_speed",
              "spin_rate", "induced_vert_break", "horz_break", "extension", "rel_height", "rel_side", "zone_speed"]


def match_season(root: Path, season: int, tolerance: float) -> tuple[pd.DataFrame, dict]:
    trackman = crosswalk._trackman(root, season)
    vb_ids = crosswalk._visualbaseball(root, season)
    games = crosswalk.map_games(trackman, vb_ids)
    extra = pd.DataFrame(load_rows(root, "pitches", season, columns=VB_COLUMNS))
    vb = vb_ids.merge(extra.drop(columns=[c for c in vb_ids.columns if c in extra.columns and c != "pitch_id"]), on="pitch_id")
    aligned = crosswalk.align_pitches(trackman, vb, games)
    table = json.loads((root / "data/tracking/player_id_crosswalk.json").read_text(encoding="utf-8"))["seasons"][str(season)]["roles"]
    ids_agree = aligned["state_agrees"].copy()
    for role, (tm_column, vb_column) in crosswalk.ROLES.items():
        lookup = {p["trackman_id"]: p["visualbaseball_id"] for p in table[role]["pairs"]}
        in_vb = set(vb[vb_column])
        linked = aligned[tm_column].astype(str).map(lambda tm: lookup.get(tm, tm if tm in in_vb else None))
        ids_agree &= linked == aligned[vb_column].astype(str)
    for column in TM_COLUMNS[5:]:
        aligned[column] = pd.to_numeric(aligned[column], errors="coerce")
    speed_gap = aligned["velocity_kmh"].astype(float) - aligned["rel_speed"]
    consistent = aligned[ids_agree]
    offset = float(speed_gap[ids_agree].median())
    fast = (speed_gap - offset).abs() <= tolerance
    matched = aligned[ids_agree & fast].copy()
    matched["speed_gap_kmh"] = speed_gap[ids_agree & fast]
    meta = {"season": season, "visualbaseball_pitches": int(len(vb)), "mapped_games": len(games), "aligned": int(len(aligned)),
            "state_and_id_consistent": int(len(consistent)), "speed_gap_median_kmh": offset,
            "speed_gap_mad_kmh": float((speed_gap[ids_agree] - offset).abs().median()),
            "outside_speed_tolerance": int((ids_agree & ~fast).sum()), "matched": int(len(matched)),
            "matched_share_of_visualbaseball": round(len(matched) / len(vb), 4)}
    keep = [c for c in VB_COLUMNS if c in matched] + TM_COLUMNS + ["half", "date_vb", "trackman_game_id", "balls_before_vb", "strikes_before_vb", "speed_gap_kmh"]
    return matched[list(dict.fromkeys(keep))].reset_index(drop=True), meta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--seasons", nargs="+", type=int, default=[2019, 2020, 2021, 2022, 2023, 2024])
    parser.add_argument("--speed-tolerance", type=float, default=3.0)
    args = parser.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    metas = []
    for season in args.seasons:
        matched, meta = match_season(ROOT, season, args.speed_tolerance)
        matched.to_parquet(out / f"matched_{season}.parquet", index=False)
        metas.append(meta); print(json.dumps(meta, ensure_ascii=False), flush=True)
    (out / "match_summary.json").write_text(json.dumps(metas, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
