"""za7.2 → za7.3(C0d) 공개 SBJ 선수 변화표. python analysis/sbj_formula/c0d_release_changes.py [기준 커밋]

기준 커밋(기본 master)의 web/data/zone_awareness/<Y>/leaderboard.json과 작업 트리의 값을 비교한다.
결과: results/c0d_release_changes.json, results/c0d_release_changes_<Y>.csv
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("results")
BASE = sys.argv[1] if len(sys.argv) > 1 else "master"


def board(text):
    d = json.loads(text)
    return d["model_version"], pd.DataFrame(d["players"]).set_index("batter_id")


res = {"base": BASE, "seasons": {}}
for y in range(2019, 2027):
    path = f"web/data/zone_awareness/{y}/leaderboard.json"
    v0, a = board(subprocess.run(["git", "show", f"{BASE}:{path}"], cwd=ROOT, capture_output=True, text=True, check=True).stdout)
    v1, b = board((ROOT / path).read_text(encoding="utf-8"))
    qa, qb = set(a.index[a.qualified_300]), set(b.index[b.qualified_300])
    q = sorted(qa & qb)
    ra = a.loc[q, "za_raw"].rank(ascending=False, method="min"); rb = b.loc[q, "za_raw"].rank(ascending=False, method="min")
    d = b.loc[q, "za_raw"] - a.loc[q, "za_raw"]; shift = (ra - rb).abs()
    common = a.index.intersection(b.index)
    res["seasons"][y] = {
        "model_version": [v0, v1], "qualified": len(q), "qualification_changes": len(qa ^ qb),
        "mean_abs_delta_sbj": float(d.abs().mean()), "max_abs_delta_sbj": float(d.abs().max()),
        "spearman": float(a.loc[q, "za_raw"].rank().corr(b.loc[q, "za_raw"].rank())),
        "max_rank_shift": int(shift.max()), "moved_5_or_more": int((shift >= 5).sum()),
        "mean_abs_delta_percentile": float((b.loc[q, "za_percentile"] - a.loc[q, "za_percentile"]).abs().mean()),
        "mean_abs_delta_sa": float((b.loc[q, "swing_aggression"] - a.loc[q, "swing_aggression"]).abs().mean()),
        # DV는 p_swing·p_zone을 쓰지 않으므로 바뀌지 않아야 한다
        "max_abs_delta_dv_per_100_all_batters": float((b.loc[common, "dv_per_100"] - a.loc[common, "dv_per_100"]).abs().max()),
        "batters": [len(a), len(b)],
    }
    pd.DataFrame({"batter_id": q, "batter_name": b.loc[q, "batter_name"].values, "sbj_za72": a.loc[q, "za_raw"].values,
                  "sbj_za73": b.loc[q, "za_raw"].values, "delta": d.values, "rank_za72": ra.values, "rank_za73": rb.values,
                  "percentile_za72": a.loc[q, "za_percentile"].values, "percentile_za73": b.loc[q, "za_percentile"].values}
                 ).sort_values("rank_za73").to_csv(OUT / f"c0d_release_changes_{y}.csv", index=False, float_format="%.4f")
    print(y, json.dumps(res["seasons"][y]), flush=True)
(OUT / "c0d_release_changes.json").write_text(json.dumps(res, indent=1) + "\n")
