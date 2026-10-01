"""W: wRC+형 판단 DV+ (리그 중심화 → 소표본 수축 → 리그 DV/100 대비 비율), Savant식 백분위 (gates.md W).

python analysis/sbj_formula/w_dv_plus.py -> results/w_dv_plus.json, results/w_dv_plus_<Y>.csv
za7.5 투구 근거와 공개 leaderboard(SBJ·현행 DV+ 비교용)만 읽는다.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from visualbaseball.zone_decision import MODEL_VERSION  # noqa: E402

OUT = Path(__file__).with_name("results")
QUAL = 300


def per_batter(df):
    g = df.groupby("batter_id"); n = g.size(); m = g.jdv.mean()
    dev = df.jdv - df.batter_id.map(m)
    se = np.sqrt((dev.groupby([df.batter_id, df.game_id]).sum() ** 2).groupby(level=0).sum()) / n
    return pd.DataFrame({"n": n, "jdv": 100 * m, "se": 100 * se})


def shrink_k(t, min_n):
    q = t[t.n >= min_n]
    sigma2 = float((q.se ** 2 * q.n).median())
    tau2 = float(q.jdvc.var(ddof=1) - (q.se ** 2).mean())
    return sigma2 / tau2 if tau2 > 0 else np.inf, sigma2, tau2


def percentile(values, reference):
    ref = np.sort(np.asarray(reference))
    lo, hi = np.searchsorted(ref, values, "left"), np.searchsorted(ref, values, "right")
    return 100 * (lo + .5 * (hi - lo)) / len(ref)


def season(y):
    report = json.loads((ROOT / f"data/metrics/zone_awareness/{y}/report.json").read_text(encoding="utf-8"))
    assert report["model_version"] == MODEL_VERSION
    df = pq.read_table(ROOT / f"data/metrics/zone_awareness/{y}/pitches.parquet",
                       columns=["game_id", "batter_id", "swing", "p_swing", "delta_v", "dv", "fold"]).to_pandas()
    df["batter_id"] = df.batter_id.astype(str)
    df["jdv"] = 2 * (df.swing - df.p_swing) * df.delta_v
    L = 100 * float(df.dv.mean()); m = 100 * float(df.jdv.mean())
    t = per_batter(df); t["jdvc"] = t.jdv - m
    k, sigma2, tau2 = shrink_k(t, QUAL)
    t["w"] = t.n / (t.n + k)
    t["plus"] = 100 * (L + t.w * t.jdvc) / L
    t["plus_raw"] = 100 * (L + t.jdvc) / L
    t["qualified"] = t.n >= QUAL
    t["pct"] = percentile(t.plus, t.plus[t.qualified])
    t["pct_raw"] = percentile(t.plus_raw, t.plus_raw[t.qualified])
    board = pd.DataFrame(json.loads((ROOT / f"web/data/zone_awareness/{y}/leaderboard.json").read_text(encoding="utf-8"))["players"])
    board["batter_id"] = board.batter_id.astype(str)
    t = t.join(board.set_index("batter_id")[["batter_name", "team", "za_raw", "za_percentile", "dv_plus", "swing_aggression"]])

    # W1: 블록 1 → 블록 2·3
    b1 = per_batter(df[df.fold == 0]); b23 = per_batter(df[df.fold != 0])
    b1["jdvc"] = b1.jdv - m; b23["jdvc"] = b23.jdv - m
    k1 = shrink_k(b1, 150)[0]
    ids = b1.index[b1.n >= 150].intersection(b23.index[b23.n >= 150])
    mse_raw = float(((b1.jdvc[ids] - b23.jdvc[ids]) ** 2).mean())
    mse_shr = float(((b1.n[ids] / (b1.n[ids] + k1) * b1.jdvc[ids] - b23.jdvc[ids]) ** 2).mean())
    # W2
    s = t[t.n >= 100]
    rho = float(s.n.rank().corr((s.plus - 100).abs().rank()))
    rho_raw = float(s.n.rank().corr((s.plus_raw - 100).abs().rank()))
    # W3
    league = float((t.plus * t.n).sum() / t.n.sum())
    # W4
    nq = t[(t.n >= 100) & ~t.qualified]; qq = t[t.qualified]
    ext = lambda p: float(((p <= 5) | (p >= 95)).mean()) if len(p) else 0.0
    w4 = {"nonqualified_100_299": len(nq), "share_extreme_nonqualified": ext(nq.pct), "share_extreme_qualified": ext(qq.pct),
          "raw_share_extreme_nonqualified": ext(nq.pct_raw), "raw_share_extreme_qualified": ext(qq.pct_raw)}
    gates = {"W1": {"mse_raw": mse_raw, "mse_shrunk": mse_shr, "batters": len(ids), "k_block1": k1, "pass": mse_shr < mse_raw},
             "W2": {"spearman": rho, "spearman_raw": rho_raw, "pass": rho >= 0},
             "W3": {"league_mean": league, "pass": abs(league - 100) <= .5},
             "W4": {**w4, "pass": w4["share_extreme_nonqualified"] <= w4["share_extreme_qualified"]}}
    gates["pass"] = all(g["pass"] for g in gates.values() if isinstance(g, dict))
    q = t[t.qualified]
    rank = lambda col: q[col].rank(ascending=False, method="min")
    small = lambda col, top: int((q.sort_values(col, ascending=not top).head(10).n < 500).sum())
    t.reset_index().rename(columns={"index": "batter_id"}).sort_values("plus", ascending=False).to_csv(
        OUT / f"w_dv_plus_{y}.csv", index=False, float_format="%.4f")
    return t, {"L": L, "league_jdv": m, "k": k, "sigma2": sigma2, "tau2": tau2, "qualified": int(t.qualified.sum()),
               "batters": len(t), "gates": gates,
               "spearman_qualified": {"vs_sbj": float(rank("plus").corr(rank("za_raw"))), "vs_dv_plus": float(rank("plus").corr(rank("dv_plus")))},
               "under_500_in_top10": {"shrunk": small("plus", True), "raw": small("plus_raw", True)},
               "under_500_in_bottom10": {"shrunk": small("plus", False), "raw": small("plus_raw", False)}}


def main():
    res = {"model_version": MODEL_VERSION, "seasons": {}}
    tables = {}
    for y in range(2019, 2027):
        tables[y], res["seasons"][y] = season(y)
        print(y, json.dumps(res["seasons"][y]["gates"]), flush=True)
    res["all_pass"] = all(s["gates"]["pass"] for s in res["seasons"].values())
    res["lee_jaehyun_percentiles"] = {y: float(tables[y].loc[tables[y].batter_name == "이재현", "pct"].iloc[0])
                                      for y in (2022, 2023, 2024, 2025) if (tables[y].batter_name == "이재현").any()}
    (OUT / "w_dv_plus.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({y: {k: v for k, v in s.items() if k != "gates"} for y, s in res["seasons"].items()}, ensure_ascii=False))
    print("all_pass", res["all_pass"], res["lee_jaehyun_percentiles"])


if __name__ == "__main__":
    main()
