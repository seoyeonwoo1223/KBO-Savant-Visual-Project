"""Where the reported-location (A) and za7.2 (B) p_zone disagree, and how much of p_zone log loss
comes from flagged takes. Read-only; ABS calls are the target, not an independent physical truth.

    python analysis/sbj_location/pzone_error_analysis.py <audit dir> <work dir>
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd

A, W = Path(sys.argv[1]), Path(sys.argv[2]); HALF_CM = 25.4; out = {}
for s in (2024, 2025, 2026):
    d = pd.read_parquet(W / f"pzone_exp_{s}.parquet"); t = d[d.swing == 0].copy()
    cs = t.event.eq("CalledStrike")
    big = t[(t.A_reported - t.B_za72).abs() > 0.4].copy()
    edges = pd.DataFrame({"side": (big.x_mid_relative.abs() * HALF_CM - HALF_CM).abs(), "top": big.top_gap_cm.abs(), "bottom": big.bottom_gap_cm.abs()})
    big["edge"] = edges.idxmin(axis=1); bcs = big.event.eq("CalledStrike")
    big["B_right"] = bcs == (big.B_za72 >= .5); big["A_right"] = bcs == (big.A_reported >= .5)
    e = {"A_B_gap_gt_0.4_takes": int(len(big)),
         "by_nearest_edge": big.groupby("edge").agg(n=("edge", "size"), B_right=("B_right", "mean"), A_right=("A_right", "mean")).round(3).to_dict("index"),
         "median_front_pz_minus_trajectory_cm": {"top_edge": round(float((big[big.edge == "top"].rep_top_gap_cm - big[big.edge == "top"].top_gap_cm).median()), 2),
                                                 "bottom_edge": round(float((big[big.edge == "bottom"].rep_bottom_gap_cm - big[big.edge == "bottom"].bottom_gap_cm).median()), 2)}}
    q = pd.read_csv(A / f"sbj_pitch_quality_{s}.csv.gz", dtype=str, usecols=["pitch_id", "flags", "review_level"] + (["tm_event"] if s == 2024 else []))
    t = t.merge(q, on="pitch_id", how="left"); y = t.event.eq("CalledStrike").astype(int); f = t["flags"].fillna("")
    for v in ("A_reported", "B_za72"):
        t["ll_" + v] = -(y * np.log(t[v]) + (1 - y) * np.log(1 - t[v]))
    masks = {"structural": t.review_level.eq("structural"), "B_NEAR_CENTER": f.str.contains("B_NEAR_CENTER"), "any_flag": t.review_level.ne("none")}
    if s == 2024: masks["vb_ball_tm_next_strike"] = t.tm_event.eq("strike") & t.event.eq("Ball")
    e["logloss_share_pct"] = {k: {"takes": int(m.sum()), "A": round(100 * t.loc[m, "ll_A_reported"].sum() / t.ll_A_reported.sum(), 1),
                                  "B": round(100 * t.loc[m, "ll_B_za72"].sum() / t.ll_B_za72.sum(), 1)} for k, m in masks.items()}
    w = t.nlargest(200, "ll_B_za72")
    e["worst_200_B_takes"] = {"flagged": int(w.review_level.ne("none").sum()), "B_NEAR_CENTER": int(f.loc[w.index].str.contains("B_NEAR_CENTER").sum()), "vb_ball": int(w.event.eq("Ball").sum())}
    out[s] = e
(W / "pzone_error_analysis.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(json.dumps(out, ensure_ascii=False, indent=1))
