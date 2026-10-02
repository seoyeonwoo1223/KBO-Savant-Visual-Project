"""X: 판단 지표 후보 5종 정식 비교 (gates.md X). python analysis/sbj_formula/x_compare.py

결과: results/x_compare.json, results/x_compare_<Y>.csv
읽기 전용. za7.6 투구 근거와 curated 타석 결과만 읽는다.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).parent))
from jdv_experiment import pa_type_map  # noqa: E402
from v_execution import WOBA, cluster_mean  # noqa: E402
from visualbaseball import zone_decision as zd  # noqa: E402
from visualbaseball.curated import load_rows  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("results")
CANDS = ("A_apr", "B_apr_neutral", "C_seager", "D_za", "E_apr_za")


def apr_from(ev, jdv_col, min_q):
    t = cluster_mean(ev[jdv_col], ev.batter_id, ev.game_id)
    players = [{"batter_id": b, "pitches_seen": int(t.n[b]), "qualified_300": bool(t.n[b] >= min_q),
                "jdv_per_100": float(100 * t["mean"][b]), "jdv_se": float(100 * t.se[b])} for b in t.index]
    zd.add_apr(players, 100 * float(ev.dv.mean()), 100 * float(ev[jdv_col].mean()))
    return pd.DataFrame(players).set_index("batter_id").apr


def pct(s, ref):
    r = np.sort(ref.to_numpy())
    lo, hi = np.searchsorted(r, s.to_numpy(), "left"), np.searchsorted(r, s.to_numpy(), "right")
    return pd.Series(100 * (lo + .5 * (hi - lo)) / len(r), index=s.index)


def candidates(ev, min_q):
    """한 표본(시즌 전체 또는 반쪽)에서 다섯 후보와 SA를 계산. min_q는 적격 투구 수."""
    ev = ev.copy()
    ev["r"] = ev.swing - ev.p_swing
    ev["jdv"] = 2 * ev.r * ev.delta_v
    ev["jdv_neutral"] = 2 * (ev.r - ev.groupby("batter_id").r.transform("mean")) * ev.delta_v
    n = ev.groupby("batter_id").size(); q = n.index[n >= min_q]
    take, swing = ev.swing == 0, ev.swing == 1
    good = (swing & (ev.delta_v > 0)) | (take & (ev.delta_v < 0))
    g = ev.assign(ht=(take & (ev.delta_v > 0)), tk=take, sel=(take & (ev.delta_v < 0)), good=good).groupby("batter_id")[["ht", "tk", "sel", "good"]].sum()
    out = pd.DataFrame({
        "n": n, "sa": 100 * ev.groupby("batter_id").r.mean(),
        "A_apr": apr_from(ev, "jdv", min_q), "B_apr_neutral": apr_from(ev, "jdv_neutral", min_q),
        "C_seager": g.sel / g.good - g.ht / g.tk, "D_za": 100 * ev.groupby("batter_id").judgment.mean()})
    out["E_apr_za"] = (pct(out.A_apr, out.A_apr[q]) + pct(out.D_za, out.D_za[q])) / 2
    return out.loc[q]


def outcomes(y):
    rows = load_rows(ROOT, "pitches", y, columns=["batter_id", "is_pa_terminal", "pa_type", "pa_result"])
    t = pd.DataFrame([r for r in rows if r["is_pa_terminal"]])
    mapping = pa_type_map(); miss = t.pa_type.isna()
    t.loc[miss, "pa_type"] = t.loc[miss, "pa_result"].map(lambda v: mapping.get(v, "out"))
    last = t.pa_result.fillna("").str[-1]
    hbp = t.pa_result.eq("사구"); bb = t.pa_type.eq("bb") & ~hbp; hr = t.pa_type.eq("hr"); hit = t.pa_type.eq("hit")
    d2, d3 = hit & last.eq("이"), hit & last.eq("삼"); s1 = hit & ~d2 & ~d3
    t = t.assign(batter_id=t.batter_id.astype(str), bb=bb, hbp=hbp, hr=hr, d2=d2, d3=d3, s1=s1,
                 on=bb | hbp | hit | hr,
                 w=bb * WOBA["bb"] + hbp * WOBA["hbp"] + s1 * WOBA["1B"] + d2 * WOBA["2B"] + d3 * WOBA["3B"] + hr * WOBA["hr"])
    g = t.groupby("batter_id"); pa = g.size(); ab = pa - g.bb.sum() - g.hbp.sum()
    return pd.DataFrame({"pa": pa, "bb_pct": g.bb.sum() / pa, "obp": g.on.sum() / pa, "woba": g.w.sum() / pa,
                         "iso": (g.d2.sum() + 2 * g.d3.sum() + 3 * g.hr.sum()) / ab.where(ab > 0)})


def main():
    full, rel, sa_corr = {}, {c: {} for c in CANDS}, {c: {} for c in CANDS}
    for y in range(2019, 2027):
        ev = pq.read_table(ROOT / f"data/metrics/zone_awareness/{y}/pitches.parquet",
                           columns=["game_id", "batter_id", "swing", "p_swing", "delta_v", "dv", "judgment"]).to_pandas()
        ev["batter_id"] = ev.batter_id.astype(str)
        full[y] = candidates(ev, 300)
        full[y].sort_values("A_apr", ascending=False).to_csv(OUT / f"x_compare_{y}.csv", float_format="%.4f")
        games = ev.game_id.astype("category").cat.codes
        a, b = candidates(ev[games % 2 == 0], 150), candidates(ev[games % 2 == 1], 150)
        ids = a.index.intersection(b.index)
        for c in CANDS:
            r = a.loc[ids, c].corr(b.loc[ids, c]); rel[c][y] = float(2 * r / (1 + r))
            sa_corr[c][y] = float(full[y][c].rank().corr(full[y].sa.rank()))
        print(y, {c: round(rel[c][y], 2) for c in CANDS}, flush=True)
    out = {y: outcomes(y) for y in range(2019, 2027)}
    frames, y2y = [], {c: [] for c in CANDS}
    for y in range(2019, 2026):
        t = full[y].join(out[y][["iso"]], how="inner").join(out[y + 1][["pa", "bb_pct", "obp", "woba"]], how="inner")
        t = t[t.pa >= 150].dropna(subset=["iso"])
        cols = list(CANDS) + ["iso", "bb_pct", "obp", "woba"]
        frames.append(pd.DataFrame({"batter": t.index, **{c: t[c] - t[c].mean() for c in cols}}))
        ids = full[y].index.intersection(full[y + 1].index)
        for c in CANDS:
            y2y[c].append(pd.DataFrame({"a": full[y].loc[ids, c], "b": full[y + 1].loc[ids, c]}))
    d = pd.concat(frames, ignore_index=True)
    rng = np.random.default_rng(20261001); bats = d.batter.unique(); groups = d.groupby("batter").indices
    picks = [np.concatenate([groups[b] for b in rng.choice(bats, len(bats), replace=True)]) for _ in range(1000)]

    def std_coef(x, c):
        X = np.column_stack([np.ones(len(x)), (x[c] - x[c].mean()) / x[c].std(), (x.iso - x.iso.mean()) / x.iso.std()])
        return np.linalg.lstsq(X, (x.woba - x.woba.mean()) / x.woba.std(), rcond=None)[0][1]

    res = {"pairs": len(d), "batters": len(bats), "candidates": {}}
    for c in CANDS:
        boots = np.array([std_coef(d.iloc[p], c) for p in picks]); point = float(std_coef(d, c))
        x1 = float(np.mean(list(rel[c].values()))); x2 = max(abs(v) for v in sa_corr[c].values())
        ci = [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))]
        res["candidates"][c] = {
            "X1_reliability_by_season": rel[c], "X1_mean": x1, "X1_pass": x1 >= .60,
            "X2_spearman_sa_by_season": sa_corr[c], "X2_max_abs": x2, "X2_pass": x2 <= .30,
            "X3_next_season": {o: float(d[c].corr(d[o])) for o in ("bb_pct", "obp", "woba")},
            "X4_std_coef_given_iso": point, "X4_ci95": ci, "X4_pass": ci[0] > 0,
            "X5_year_to_year": float(pd.concat(y2y[c]).corr().iloc[0, 1])}
        res["candidates"][c]["all_required_pass"] = all(res["candidates"][c][k] for k in ("X1_pass", "X2_pass", "X4_pass"))
    passing = [c for c in CANDS if res["candidates"][c]["all_required_pass"]]
    rec = None
    if passing:
        best = max(passing, key=lambda c: res["candidates"][c]["X4_std_coef_given_iso"])
        close = [c for c in passing if res["candidates"][c]["X4_std_coef_given_iso"] >= res["candidates"][best]["X4_ci95"][0]
                 and res["candidates"][best]["X4_std_coef_given_iso"] <= res["candidates"][c]["X4_ci95"][1]]
        rec = max(close, key=lambda c: res["candidates"][c]["X1_mean"])
    res["passing"] = passing; res["recommended"] = rec
    t25 = full[2025]
    names = pd.DataFrame(json.loads((ROOT / "web/data/zone_awareness/2025/leaderboard.json").read_text(encoding="utf-8"))["players"])
    names = names.assign(batter_id=names.batter_id.astype(str)).set_index("batter_id").batter_name
    res["2025_top10"] = {c: [names.get(i, i) for i in t25.sort_values(c, ascending=False).index[:10]] for c in CANDS}
    res["2025_bottom5"] = {c: [names.get(i, i) for i in t25.sort_values(c).index[:5]] for c in CANDS}
    (OUT / "x_compare.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for c in CANDS:
        v = res["candidates"][c]
        print(f"{c:14s} X1 {v['X1_mean']:.2f} X2 max|ρ| {v['X2_max_abs']:.2f} X3 {({k: round(x, 3) for k, x in v['X3_next_season'].items()})} "
              f"X4 {v['X4_std_coef_given_iso']:+.3f} [{v['X4_ci95'][0]:+.3f},{v['X4_ci95'][1]:+.3f}] X5 {v['X5_year_to_year']:.2f} pass={v['all_required_pass']}")
    print("passing", passing, "recommended", rec)


if __name__ == "__main__":
    main()
