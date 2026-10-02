"""R: 위치(구역) × 스트라이크별 스윙·테이크 가치를 블록 밖 실현 가치로 교차 보정한 뒤 APR 재계산 (gates.md R).

python analysis/sbj_formula/r_location_calibration.py -> results/r_location.json, results/r_location_<Y>.csv
읽기 전용. za7.6 투구 근거, 운영 load_rows 행(캐시), 공개 leaderboard, curated 타석 결과만 읽는다.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).parent))
import sbj_exp as E  # noqa: E402
from v_execution import cluster_mean, woba  # noqa: E402
from visualbaseball import zone_decision as zd  # noqa: E402

ROOT = E.ROOT
OUT = Path(__file__).with_name("results")
PRIOR = 500


def apr_table(ev, dv_col, jdv_col):
    t = cluster_mean(ev[jdv_col], ev.batter_id, ev.game_id)
    players = [{"batter_id": b, "pitches_seen": int(t.n[b]), "qualified_300": bool(t.n[b] >= 300),
                "jdv_per_100": float(100 * t["mean"][b]), "jdv_se": float(100 * t.se[b])} for b in t.index]
    zd.add_apr(players, 100 * float(ev[dv_col].mean()), 100 * float(ev[jdv_col].mean()))
    out = pd.DataFrame(players).set_index("batter_id")
    q = out[out.qualified_300]
    out.attrs["reliability"] = float(1 - (q.jdv_se ** 2).mean() / q.jdv_per_100.var(ddof=1))
    return out


def cell_rms(df, value_col):
    """구역 × 행동 칸 평균 잔차의 투구 가중 RMS (100구당)."""
    g = (100 * df[value_col]).groupby([df.region, df.swing])
    m, n = g.mean(), g.size()
    return float(np.sqrt((n * m ** 2).sum() / n.sum()))


def season(y):
    rows = E.rows_for(y); ordered, fold, blocks = E.ordered_folds(rows)
    ev = pq.read_table(ROOT / f"data/metrics/zone_awareness/{y}/pitches.parquet",
                       columns=["game_id", "batter_id", "event", "region", "strikes_before", "swing", "p_swing",
                                "delta_v", "v_swing", "v_take", "dv", "fold"]).to_pandas()
    assert len(ev) == len(ordered) and (ev.game_id.to_numpy() == np.array([r["game_id"] for r in ordered])).all()
    assert (ev.event.to_numpy() == np.array([r["event"] for r in ordered])).all() and (ev.fold.to_numpy() == fold).all()
    ev["batter_id"] = ev.batter_id.astype(str)
    ev["cell"] = ev.region.astype(str) + "|" + ev.strikes_before.astype(str)
    ev["realized"] = np.nan; ev["c_swing"] = 0.0; ev["c_take"] = 0.0
    corrections = {}
    for f in range(3):
        held = (ev.fold == f).to_numpy(); train = ~held
        re = zd.RunExpectancy([ordered[i] for i in np.flatnonzero(train)])
        real_train = re.target([ordered[i] for i in np.flatnonzero(train)])
        ev.loc[held, "realized"] = re.target([ordered[i] for i in np.flatnonzero(held)])
        tr = ev[train].assign(real=real_train)
        for action, vcol, ccol in ((1, "v_swing", "c_swing"), (0, "v_take", "c_take")):
            sub = tr[tr.swing == action]
            g = (sub.real - sub[vcol]).groupby(sub.cell)
            c = g.sum() / (g.size() + PRIOR)
            ev.loc[held, ccol] = ev.loc[held, "cell"].map(c).fillna(0).to_numpy()
            corrections.setdefault(f, {})[action] = {k: float(100 * v) for k, v in c.items()}
    ev["v_chosen"] = np.where(ev.swing == 1, ev.v_swing, ev.v_take)
    ev["v_chosen_r"] = ev.v_chosen + np.where(ev.swing == 1, ev.c_swing, ev.c_take)
    ev["res_before"] = ev.realized - ev.v_chosen; ev["res_after"] = ev.realized - ev.v_chosen_r
    r1_before, r1_after = cell_rms(ev, "res_before"), cell_rms(ev, "res_after")
    ev["dv_r_delta"] = ev.delta_v + ev.c_swing - ev.c_take
    ev["dv_r"] = np.where(ev.swing == 1, ev.dv_r_delta, -ev.dv_r_delta)
    ev["jdv_base"] = 2 * (ev.swing - ev.p_swing) * ev.delta_v
    ev["jdv_r"] = 2 * (ev.swing - ev.p_swing) * ev.dv_r_delta
    base, cal = apr_table(ev, "dv", "jdv_base"), apr_table(ev, "dv_r", "jdv_r")
    board = pd.DataFrame(json.loads((ROOT / f"web/data/zone_awareness/{y}/leaderboard.json").read_text(encoding="utf-8"))["players"])
    board["batter_id"] = board.batter_id.astype(str); board = board.set_index("batter_id")
    sanity = float((base.apr - board.apr[base.index]).abs().max())
    q = board.index[board.qualified_300]; sa = board.swing_aggression[q]
    rho = lambda s: float(s[q].rank().corr(sa.rank()))
    region_after = (100 * ev.res_after).groupby([ev.region, ev.swing]).mean().unstack()
    region_before = (100 * ev.res_before).groupby([ev.region, ev.swing]).mean().unstack()
    tab = pd.DataFrame({"batter_name": board.batter_name[q], "team": board.team[q], "pitches": board.pitches_seen[q], "sa": sa,
                        "za": board.za_raw[q], "apr": base.apr[q], "apr_r": cal.apr[q]})
    tab["rank_apr"] = tab.apr.rank(ascending=False, method="min").astype(int)
    tab["rank_apr_r"] = tab.apr_r.rank(ascending=False, method="min").astype(int)
    tab.sort_values("apr_r", ascending=False).to_csv(OUT / f"r_location_{y}.csv", float_format="%.4f")
    out = {"R1": {"rms_before": r1_before, "rms_after": r1_after, "reduction": 1 - r1_after / r1_before, "pass": r1_after <= .5 * r1_before,
                  "region_residual_before": {f"{k}|{'swing' if a else 'take'}": float(region_before.loc[k, a]) for k in region_before.index for a in (0, 1)},
                  "region_residual_after": {f"{k}|{'swing' if a else 'take'}": float(region_after.loc[k, a]) for k in region_after.index for a in (0, 1)}},
           "R2": {"spearman_apr_sa": rho(base.apr), "spearman_apr_r_sa": rho(cal.apr), "delta": rho(cal.apr) - rho(base.apr),
                  "mean_abs_delta_apr": float((cal.apr[q] - base.apr[q]).abs().mean()), "max_abs_delta_apr": float((cal.apr[q] - base.apr[q]).abs().max()),
                  "spearman_apr_vs_apr_r": float(base.apr[q].rank().corr(cal.apr[q].rank()))},
           "R4": {"reliability_base": base.attrs["reliability"], "reliability_r": cal.attrs["reliability"], "pass": cal.attrs["reliability"] >= .60},
           "corrections_runs_per_100_by_block": corrections, "sanity_max_abs_apr_vs_published": sanity}
    return out, tab


def main():
    res, tabs = {"seasons": {}}, {}
    for y in range(2019, 2027):
        res["seasons"][y], tabs[y] = season(y)
        s = res["seasons"][y]
        print(y, json.dumps({"R1": {k: s["R1"][k] for k in ("rms_before", "rms_after", "reduction", "pass")}, "R2": s["R2"], "R4": s["R4"],
                             "sanity": s["sanity_max_abs_apr_vs_published"]}), flush=True)
    res["R1_all_pass"] = all(s["R1"]["pass"] for s in res["seasons"].values())
    res["R4_all_pass"] = all(s["R4"]["pass"] for s in res["seasons"].values())
    res["R2_seasons_delta_ge_0.10"] = sum(s["R2"]["delta"] >= .10 for s in res["seasons"].values())
    res["R2_verdict_artifact"] = res["R2_seasons_delta_ge_0.10"] >= 6
    w = {y: woba(y) for y in range(2020, 2027)}
    frames = []
    for y in range(2019, 2026):
        t = tabs[y].join(w[y + 1], how="inner"); t = t[t.pa >= 150]
        frames.append(pd.DataFrame({"batter": t.index, **{c: t[c] - t[c].mean() for c in ("apr", "apr_r", "sa", "woba")}}))
    d = pd.concat(frames, ignore_index=True)

    def coefs(x, col):
        X = np.column_stack([np.ones(len(x)), x[col], x.sa])
        return np.linalg.lstsq(X, x.woba, rcond=None)[0]

    rng = np.random.default_rng(20261001); ids = d.batter.unique(); groups = d.groupby("batter").indices
    picks = [np.concatenate([groups[b] for b in rng.choice(ids, len(ids), replace=True)]) for _ in range(1000)]
    r3 = {"pairs": len(d), "batters": len(ids), "corr_next_woba": {"apr": float(d.apr.corr(d.woba)), "apr_r": float(d.apr_r.corr(d.woba))}}
    for col in ("apr", "apr_r"):
        point = coefs(d, col); boots = np.array([coefs(d.iloc[p], col) for p in picks])
        r3[f"with_{col}"] = {"coef_metric": float(point[1]), "coef_sa": float(point[2]),
                             "coef_sa_ci95": [float(np.percentile(boots[:, 2], 2.5)), float(np.percentile(boots[:, 2], 97.5))]}
    res["R3"] = r3
    (OUT / "r_location.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "seasons"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
