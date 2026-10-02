"""진단(읽기 전용): SEAGER식 두 비율과 APR 성분의 관계. python analysis/sbj_formula/seager_components.py

- hittable_taken: 테이크 중 ΔV > 0(쳤어야 할 공)의 비율 (SEAGER의 Hittable Pitches Taken %, 낮을수록 좋음)
- selectivity: 좋은 결정(ΔV>0 스윙, ΔV<0 테이크) 중 ΔV<0 테이크의 비율 (SEAGER의 선택성, 높을수록 좋음)
- jdv_swing / jdv_take: 판단 DV(APR 입력)의 스윙·테이크 몫 (100구당, 합 = 판단 DV)
적격(300구 이상) 타자. 신뢰도는 경기 홀짝 반분 Spearman-Brown, 결과: results/seager_components.json
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("results")


def stats(df):
    take, swing = df.swing == 0, df.swing == 1
    good = (swing & (df.delta_v > 0)) | (take & (df.delta_v < 0))
    jdv = 2 * (df.swing - df.p_swing) * df.delta_v
    g = df.assign(jdv_swing=jdv.where(swing, 0.0), jdv_take=jdv.where(take, 0.0), jdv=jdv,
                  ht=(take & (df.delta_v > 0)).astype(float), tk=take.astype(float),
                  sel=(take & (df.delta_v < 0)).astype(float), good=good.astype(float), sa=df.swing - df.p_swing).groupby("batter_id")
    s = g[["jdv_swing", "jdv_take", "jdv", "ht", "tk", "sel", "good", "sa"]].sum(); n = g.size()
    return pd.DataFrame({"n": n, "jdv_swing": 100 * s.jdv_swing / n, "jdv_take": 100 * s.jdv_take / n, "jdv": 100 * s.jdv / n,
                         "hittable_taken": s.ht / s.tk, "selectivity": s.sel / s.good,
                         "sa": 100 * s.sa / n})


out = {}
for y in range(2019, 2027):
    df = pq.read_table(ROOT / f"data/metrics/zone_awareness/{y}/pitches.parquet",
                       columns=["game_id", "batter_id", "swing", "p_swing", "delta_v"]).to_pandas()
    df["batter_id"] = df.batter_id.astype(str)
    full = stats(df); q = full.index[full.n >= 300]
    board = pd.DataFrame(json.loads((ROOT / f"web/data/zone_awareness/{y}/leaderboard.json").read_text(encoding="utf-8"))["players"])
    board["batter_id"] = board.batter_id.astype(str); board = board.set_index("batter_id")
    t = full.loc[q].join(board[["apr", "za_raw"]])
    games = df.game_id.astype("category").cat.codes
    a, b = stats(df[games % 2 == 0]), stats(df[games % 2 == 1])
    ids = a.index[a.n >= 150].intersection(b.index[b.n >= 150])
    rel = {}
    for c in ("jdv", "jdv_swing", "jdv_take", "hittable_taken", "selectivity"):
        r = a.loc[ids, c].corr(b.loc[ids, c]); rel[c] = float(2 * r / (1 + r))
    sp = lambda x, z: float(t[x].rank().corr(t[z].rank()))
    var = t.jdv.var()
    out[y] = {"qualified": len(q), "split_half_reliability": rel,
              "jdv_variance_share": {"swing": float(np.cov(t.jdv_swing, t.jdv)[0, 1] / var), "take": float(np.cov(t.jdv_take, t.jdv)[0, 1] / var)},
              "spearman": {"apr_vs_hittable_taken": sp("apr", "hittable_taken"), "apr_vs_selectivity": sp("apr", "selectivity"),
                           "hittable_taken_vs_sa": sp("hittable_taken", "sa"), "selectivity_vs_sa": sp("selectivity", "sa"),
                           "jdv_swing_vs_jdv_take": sp("jdv_swing", "jdv_take"), "apr_vs_sa": sp("apr", "sa"), "apr_vs_za": sp("apr", "za_raw")}}
(OUT / "seager_components.json").write_text(json.dumps(out, indent=1) + "\n")
for y, v in out.items():
    print(y, {k: round(x, 2) for k, x in v["split_half_reliability"].items()}, {k: round(x, 2) for k, x in v["jdv_variance_share"].items()}, {k: round(x, 2) for k, x in v["spearman"].items()})
