"""SBJ 현 산식 진단 (읽기 전용). 채점된 투구 근거 data/metrics/zone_awareness/<Y>/pitches.parquet만 읽는다.

python analysis/sbj_formula/diagnose.py  ->  analysis/sbj_formula/results/diagnose.json
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("results")
COLS = ["game_id", "batter_id", "swing", "p_swing", "p_zone", "judgment", "dv", "fold", "region", "strikes_before", "balls_before", "event", "inning_half"]
QUAL = 300


def per_batter(df, key="judgment"):
    """점수(100·mean)와 경기 군집 표준오차."""
    g = df.groupby("batter_id")
    n = g.size()
    score = 100 * g[key].mean()
    dev = df[key] - df["batter_id"].map(g[key].mean())
    game_sum = dev.groupby([df["batter_id"], df["game_id"]]).sum()
    se = 100 * np.sqrt((game_sum ** 2).groupby(level=0).sum()) / n
    return pd.DataFrame({"n": n, "score": score, "se": se})


def reliability(t):
    var = t.score.var(ddof=1)
    noise = (t.se ** 2).mean()
    return var, noise, 1 - noise / var


def split_half(df, key="judgment", min_n=150):
    game_no = df.game_id.astype("category").cat.codes
    a = per_batter(df[game_no % 2 == 0], key); b = per_batter(df[game_no % 2 == 1], key)
    ids = a.index[(a.n >= min_n)].intersection(b.index[b.n >= min_n])
    r = float(np.corrcoef(a.score[ids], b.score[ids])[0, 1])
    return {"batters": len(ids), "r": r, "spearman_brown": 2 * r / (1 + r)}


def season(y):
    path = ROOT / f"data/metrics/zone_awareness/{y}/pitches.parquet"
    cols = [c for c in COLS if c in pq.read_schema(path).names]
    df = pq.read_table(path, columns=cols).to_pandas()
    df["batter_id"] = df.batter_id.astype(str)
    df["sa"] = df.swing - df.p_swing
    df["w"] = 2 * df.p_zone - 1
    out = {"pitches": len(df)}
    t = per_batter(df)
    q = t[t.n >= QUAL]
    var, noise, rel = reliability(q)
    tau2 = var - noise
    sigma2_pitch = float((q.se ** 2 * q.n).median())  # 투구 1개당 잡음 분산 (중앙값)
    need = {str(R): int(np.ceil(R / (1 - R) * sigma2_pitch / tau2)) if tau2 > 0 else None for R in (0.5, 0.7, 0.8)}
    out["qualified"] = {"batters": len(q), "median_n": int(q.n.median()), "sd_score": float(np.sqrt(var)),
                        "median_se": float(q.se.median()), "reliability_1_minus_se2_over_var": float(rel),
                        "signal_sd": float(np.sqrt(max(tau2, 0))), "pitches_for_reliability": need,
                        "shrink_factor_at_median_n": float(tau2 / (tau2 + sigma2_pitch / q.n.median())) if tau2 > 0 else None}
    out["split_half_even_odd_games"] = split_half(df)
    # 블록 재현성: 현 report(dv) 재현 + SBJ
    blk = {}
    for key in ("dv", "judgment"):
        rows = []
        for a, b in ((0, 1), (1, 2), (0, 2)):
            ta = per_batter(df[df.fold == a], key); tb = per_batter(df[df.fold == b], key)
            ids = ta.index[ta.n >= 150].intersection(tb.index[tb.n >= 150])
            ra = reliability(ta.loc[ids])[2]; rb = reliability(tb.loc[ids])[2]
            r = float(np.corrcoef(ta.score[ids], tb.score[ids])[0, 1])
            rows.append({"blocks": [a + 1, b + 1], "batters": len(ids), "r": r,
                         "expected_r_if_stable": float(np.sqrt(max(ra, 0) * max(rb, 0)))})
        blk[key] = rows
    out["block_reproducibility"] = blk
    # 공격성 누수: SBJ = 100·[cov_i(S−q, w) + mean(S−q)·mean(w)]
    g = df.groupby("batter_id")
    lvl = 100 * g.sa.mean() * g.w.mean()
    qi = q.index
    out["aggression"] = {"corr_sbj_sa": float(np.corrcoef(q.score, 100 * g.sa.mean()[qi])[0, 1]),
                         "sd_level_term": float(lvl[qi].std()), "league_mean_w": float(df.w.mean())}
    # 가중치 구조
    aw = df.w.abs()
    out["weight"] = {"share_abs_w_lt_0.5": float((aw < .5).mean()), "share_abs_w_lt_0.9": float((aw < .9).mean()),
                     "share_abs_w_ge_0.98": float((aw >= .98).mean())}
    # 구역별 기여: 선수 SBJ 분산 중 각 구역 몫 (cov(region contribution, total)/var)
    contrib = df.assign(c=100 * df.judgment).pivot_table(index="batter_id", columns="region", values="c", aggfunc="sum").fillna(0)
    contrib = contrib.div(t.n, axis=0).loc[qi]
    tot = contrib.sum(axis=1)
    out["region_variance_share"] = {r: float(np.cov(contrib[r], tot)[0, 1] / tot.var()) for r in contrib.columns}
    out["region_pitch_share"] = {k: float(v) for k, v in df.region.value_counts(normalize=True).items()}
    # 스윙 vs 테이크 몫
    sw = (100 * df.judgment * df.swing).groupby(df.batter_id).sum().div(t.n)[qi]
    out["swing_side_variance_share"] = float(np.cov(sw, tot)[0, 1] / tot.var())
    # p_zone 카운트 보정 (경계 테이크 0.1<p_zone<0.9): 관측 CalledStrike 비율 − 평균 p_zone
    tk = df[(df.swing == 0) & df.p_zone.between(.1, .9)]
    cs = (tk.event == "CalledStrike").astype(float)
    out["pzone_count_calibration"] = {f"{s}strike": {"n": int((tk.strikes_before == s).sum()),
        "observed_minus_pred": float((cs - tk.p_zone)[tk.strikes_before == s].mean())} for s in (0, 1, 2)}
    # 구장 입력의 팀 성향 흡수: 팀별 홈/원정 평균 SA·SBJ (팀 코드 = game_id 원정 8:10, 홈 10:12)
    home = df.inning_half == "bottom"
    team = np.where(home, df.game_id.str[10:12], df.game_id.str[8:10])
    rows = {}
    for key in ("sa", "judgment"):
        m = (100 * df[key]).groupby([team, home]).mean().unstack()
        rows[key] = {"sd_team_home": float(m[True].std()), "sd_team_away": float(m[False].std()),
                     "corr_home_away": float(np.corrcoef(m[True], m[False])[0, 1])}
    out["team_home_away"] = rows
    return out


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    res = {}
    for y in range(2019, 2027):
        p = ROOT / f"data/metrics/zone_awareness/{y}/pitches.parquet"
        if p.exists():
            res[y] = season(y); print(y, json.dumps(res[y]["qualified"]), json.dumps(res[y]["block_reproducibility"]["judgment"]))
    (OUT / "diagnose.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
