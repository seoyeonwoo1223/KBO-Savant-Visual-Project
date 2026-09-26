"""타석 흐름 의심 행이 ABS 시즌 ZA 입력에 얼마나 들어가는지 (연구용, 산출물은 바꾸지 않음).

    PYTHONPATH=src python analysis/trajectory_audit/pa_flow_exposure.py \\
        --audit /tmp/paflow --za "/tmp/za/pitches_{season}.parquet" --out /tmp/paflow/za_exposure.json

--audit  pa_flow_audit.py 출력 디렉터리
--za     로컬 ZA 빌드의 투구 단위 출력(zone_decision.score_crossfit 결과를 그대로 저장한 parquet).
         pitch_id가 없으므로 zone_decision.load_rows와 같은 선택·정렬을 재현해 붙이고, 경기·볼카운트·구속으로
         정렬이 맞는지 확인한다.

행을 빼고 선수 평균을 다시 내는 값은 재적합 없는 규모 확인이다. 코드가 틀린 행의 올바른 처리는 삭제가 아니라
원본 확인 후 재분류이며, 여기서는 그 방향을 정하지 않는다.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from visualbaseball import zone_decision as zd
from visualbaseball.curated import load_rows
from visualbaseball.swing_take import _eligible

ROOT = Path(__file__).resolve().parents[2]
PA_FLAGS = ("K_CONT", "BB_CONT", "X_NONLAST", "END_MISMATCH", "SPLIT_SAME", "SPLIT_PCHANGE")


def za_rows(season: int, pattern: str) -> pd.DataFrame:
    rows = zd.load_curated_rows(ROOT, "pitches", season)
    rows, _ = zd.reliable_halves(rows, zd.load_curated_rows(ROOT, "events", season))
    keep = sorted((r for r in rows if _eligible(r) and r.get("batter_id") and r.get("batter_name") and zd.outcome(r) is not None),
                  key=lambda r: r["game_id"])
    za = pd.read_parquet(pattern.format(season=season), columns=["game_id", "balls_before", "velocity_kmh", "batter_id", "swing", "judgment", "dv"])
    ok = (len(keep) == len(za) and all(r["game_id"] == g and r["balls_before"] == b for r, g, b in zip(keep, za.game_id, za.balls_before))
          and np.allclose([float(r["velocity_kmh"]) for r in keep], za.velocity_kmh.astype(float)))
    if not ok:
        raise SystemExit(f"{season}: ZA 출력과 curated 선택 순서가 맞지 않음")
    za.insert(0, "pitch_id", [r["pitch_id"] for r in keep])
    return za


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", required=True); parser.add_argument("--za", required=True); parser.add_argument("--out", required=True)
    parser.add_argument("--seasons", nargs="+", type=int, default=[2024, 2025, 2026])
    args = parser.parse_args()
    audit = Path(args.audit); result = {}
    for season in args.seasons:
        za = za_rows(season, args.za)
        pa_id = pd.DataFrame(load_rows(ROOT, "pitches", season, columns=["pitch_id", "pa_id"]))
        za = za.merge(pa_id, on="pitch_id", how="left")
        flagged = pd.read_csv(audit / f"flagged_pas_{season}.csv", dtype=str)
        sets = {"pa_flow_rules": za.pa_id.isin(flagged.loc[flagged["flags"].str.contains("|".join(PA_FLAGS)), "pa_id"]),
                "duplicate_rows_pa": za.pa_id.isin(flagged.loc[flagged["flags"].str.contains("DUP_"), "pa_id"]),
                "B_near_center_0.8": za.pitch_id.isin(pd.read_csv(audit / f"b_near_center_{season}.csv").pitch_id)}
        if (audit / f"count_mismatch_{season}.csv").exists():
            sets["trackman_count_mismatch"] = za.pitch_id.isin(pd.read_csv(audit / f"count_mismatch_{season}.csv").pitch_id)
            sets["trackman_B_is_strike"] = za.pitch_id.isin(pd.read_csv(audit / f"b_called_strike_by_trackman_{season}.csv").pitch_id)
        sets["any"] = np.logical_or.reduce([s.to_numpy() for s in sets.values()])
        take = za.swing == 0
        size = za.groupby("batter_id").size(); qualified = size[size >= 300].index
        def per_batter(frame):
            g = frame[frame.batter_id.isin(qualified)].groupby("batter_id")
            return pd.DataFrame({"za": 100 * g.judgment.mean(), "dv100": 100 * g.dv.sum() / g.size()})
        base = per_batter(za)
        entry = {"za_rows": int(len(za)), "takes": int(take.sum()), "qualified_batters": int(len(qualified))}
        for name, sel in sets.items():
            sel = pd.Series(np.asarray(sel, dtype=bool), index=za.index)
            diff = (per_batter(za[~sel]) - base).abs()
            entry[name] = {"rows": int(sel.sum()), "share_pct": round(100 * float(sel.mean()), 3),
                           "takes_in_pzone_training": int((sel & take).sum()), "batters_touched": int(za[sel].batter_id.nunique()),
                           "drop_rows_no_refit": {"max_abs_dZA": round(float(diff.za.max()), 3), "p95_abs_dZA": round(float(diff.za.quantile(.95)), 3),
                                                  "max_abs_dDV100": round(float(diff.dv100.max()), 3), "p95_abs_dDV100": round(float(diff.dv100.quantile(.95)), 3)}}
        result[season] = entry
        print(season, json.dumps(entry, ensure_ascii=False), flush=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
