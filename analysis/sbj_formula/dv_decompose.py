"""진단: DV/100을 타자 판단 몫과 받은 공 구성 몫으로 나눈다 (읽기 전용).

DV/100 = 100·mean((2S−1)·ΔV) = 2·100·mean((S − p_swing)·ΔV)  [판단: 리그 정책 대비]
                                 + 100·mean((2·p_swing − 1)·ΔV) [기대: 받은 공과 리그 정책만으로 정해짐]
ΔV = V_swing − V_take. python analysis/sbj_formula/dv_decompose.py -> results/dv_decompose.json
"""
import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
out = {}
for y in range(2019, 2027):
    df = pq.read_table(ROOT / f"data/metrics/zone_awareness/{y}/pitches.parquet",
                       columns=["batter_id", "swing", "p_swing", "p_zone", "delta_v", "dv", "judgment", "strikes_before", "balls_before"]).to_pandas()
    df["decision"] = 2 * (df.swing - df.p_swing) * df.delta_v
    df["expected"] = (2 * df.p_swing - 1) * df.delta_v
    assert np.allclose(df.dv, df.decision + df.expected)
    g = df.groupby("batter_id"); n = g.size(); q = n[n >= 300].index
    m = 100 * g[["dv", "decision", "expected", "judgment"]].mean().loc[q]
    var = m.dv.var()
    out[y] = {
        "qualified": len(q),
        "sd": {k: float(m[k].std()) for k in ("dv", "decision", "expected", "judgment")},
        "variance_share_of_dv": {k: float(np.cov(m[k], m.dv)[0, 1] / var) for k in ("decision", "expected")},
        "spearman": {"dv_vs_decision": float(m.dv.rank().corr(m.decision.rank())),
                     "dv_vs_expected": float(m.dv.rank().corr(m.expected.rank())),
                     "sbj_vs_dv": float(m.judgment.rank().corr(m.dv.rank())),
                     "sbj_vs_decision": float(m.judgment.rank().corr(m.decision.rank()))},
        # 카운트별 |ΔV| 평균: 상황 가중이 실제로 얼마나 다른지
        "mean_abs_delta_v_by_count": {f"{b}-{s}": float(x.delta_v.abs().mean()) for (b, s), x in df.groupby(["balls_before", "strikes_before"])},
    }
    print(y, json.dumps({k: out[y][k] for k in ("sd", "variance_share_of_dv", "spearman")}))
(Path(__file__).with_name("results") / "dv_decompose.json").write_text(json.dumps(out, indent=1) + "\n")
