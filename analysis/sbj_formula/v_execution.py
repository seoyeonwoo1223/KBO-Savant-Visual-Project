"""V: APR이 타자 본인의 스윙 실행 능력을 반영하지 않아 공격적·정타형 타자를 과소평가하는가 (gates.md V).

python analysis/sbj_formula/v_execution.py -> results/v_execution.json, results/v_execution_<Y>.csv
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
from jdv_experiment import pa_type_map  # noqa: E402
from visualbaseball import zone_decision as zd  # noqa: E402
from visualbaseball.curated import load_rows  # noqa: E402

ROOT = E.ROOT
OUT = Path(__file__).with_name("results")
WOBA = {"bb": .69, "hbp": .72, "1B": .88, "2B": 1.25, "3B": 1.58, "hr": 2.03}


def cluster_mean(values, batters, games):
    """타자별 평균과 경기 군집 표준오차."""
    df = pd.DataFrame({"v": values, "b": batters, "g": games})
    g = df.groupby("b"); n = g.size(); m = g.v.mean()
    dev = df.v - df.b.map(m)
    se = np.sqrt((dev.groupby([df.b, df.g]).sum() ** 2).groupby(level=0).sum()) / n
    return pd.DataFrame({"n": n, "mean": m, "se": se})


def shrunk_execution(sw, qualified):
    """스윙 실행 잔차를 리그 중심화 후 n/(n+k)로 수축. k는 적격 타자 적률법."""
    t = cluster_mean(sw.resid - sw.resid.mean(), sw.batter_id, sw.game_id)
    q = t.loc[t.index.intersection(qualified)]
    sigma2 = float((q.se ** 2 * q.n).median()); tau2 = float(q["mean"].var(ddof=1) - (q.se ** 2).mean())
    k = sigma2 / tau2 if tau2 > 0 else np.inf
    w = t.n / (t.n + k) if np.isfinite(k) else 0 * t.n
    return w * t["mean"], k, tau2


def woba(y):
    rows = load_rows(ROOT, "pitches", y, columns=["batter_id", "is_pa_terminal", "pa_type", "pa_result"])
    t = pd.DataFrame([r for r in rows if r["is_pa_terminal"]])
    mapping = pa_type_map(); miss = t.pa_type.isna()
    t.loc[miss, "pa_type"] = t.loc[miss, "pa_result"].map(lambda v: mapping.get(v, "out"))
    last = t.pa_result.fillna("").str[-1]
    kind = np.where(t.pa_result.eq("사구"), "hbp", np.where(t.pa_type.eq("bb"), "bb", np.where(t.pa_type.eq("hr"), "hr",
                    np.where(t.pa_type.eq("hit"), np.where(last.eq("이"), "2B", np.where(last.eq("삼"), "3B", "1B")), "out"))))
    t["w"] = pd.Series(kind).map(WOBA).fillna(0).to_numpy()
    g = t.assign(batter_id=t.batter_id.astype(str)).groupby("batter_id")
    return pd.DataFrame({"pa": g.size(), "woba": g.w.mean()})


def season(y):
    rows = E.rows_for(y); ordered, fold, _ = E.ordered_folds(rows)
    ev = pq.read_table(ROOT / f"data/metrics/zone_awareness/{y}/pitches.parquet",
                       columns=["game_id", "batter_id", "event", "swing", "p_swing", "delta_v", "v_swing", "dv", "fold"]).to_pandas()
    assert len(ev) == len(ordered) and (ev.game_id.to_numpy() == np.array([r["game_id"] for r in ordered])).all()
    assert (ev.event.to_numpy() == np.array([r["event"] for r in ordered])).all()
    ev["batter_id"] = ev.batter_id.astype(str)
    ev["realized"] = zd.RunExpectancy(rows).target(ordered)
    ev["resid"] = ev.realized - ev.v_swing
    board = pd.DataFrame(json.loads((ROOT / f"web/data/zone_awareness/{y}/leaderboard.json").read_text(encoding="utf-8"))["players"])
    board["batter_id"] = board.batter_id.astype(str); board = board.set_index("batter_id")
    qualified = board.index[board.qualified_300]
    sw = ev[ev.swing == 1]

    # V1: 전체 시즌 수축 실행 잔차와 SA, 반분 신뢰도
    e_full, k_full, tau2 = shrunk_execution(sw, qualified)
    games = sw.game_id.astype("category").cat.codes
    halves = [cluster_mean(h.resid, h.batter_id, h.game_id) for h in (sw[games % 2 == 0], sw[games % 2 == 1])]
    ids = halves[0].index[halves[0].n >= 100].intersection(halves[1].index[halves[1].n >= 100]).intersection(qualified)
    r = halves[0].loc[ids, "mean"].corr(halves[1].loc[ids, "mean"]); rel = float(2 * r / (1 + r))
    q = board.loc[qualified]
    v1 = {"spearman_e_vs_sa": float(e_full[qualified].rank().corr(q.swing_aggression.rank())), "split_half_reliability": rel,
          "k_swings": float(k_full), "true_sd_runs_per_100_swings": float(100 * np.sqrt(max(tau2, 0)))}

    # APR_exec: 블록 교차 추정한 실행 잔차를 ΔV에 더함
    e_cross = np.zeros(len(ev))
    for f in range(3):
        e_f, _, _ = shrunk_execution(sw[sw.fold != f], qualified)
        m = (ev.fold == f).to_numpy()
        e_cross[m] = ev.batter_id[m].map(e_f).fillna(0).to_numpy()
    ev["jdv_exec"] = 2 * (ev.swing - ev.p_swing) * (ev.delta_v + e_cross)
    ev["jdv_base"] = 2 * (ev.swing - ev.p_swing) * ev.delta_v
    out = {}
    for name, col in (("base", "jdv_base"), ("exec", "jdv_exec")):
        t = cluster_mean(ev[col], ev.batter_id, ev.game_id)
        players = [{"batter_id": b, "pitches_seen": int(t.n[b]), "qualified_300": bool(t.n[b] >= 300),
                    "jdv_per_100": float(100 * t["mean"][b]), "jdv_se": float(100 * t.se[b])} for b in t.index]
        zd.add_apr(players, 100 * float(ev.dv.mean()), 100 * float(ev[col].mean()))
        out[name] = pd.DataFrame(players).set_index("batter_id")
    base, ex = out["base"], out["exec"]
    sanity = float((base.apr - board.apr[base.index]).abs().max())
    sa = q.swing_aggression
    rho = lambda s: float(s[qualified].rank().corr(sa.rank()))
    v2 = {"spearman_apr_sa": rho(base.apr), "spearman_apr_exec_sa": rho(ex.apr), "delta": rho(ex.apr) - rho(base.apr),
          "mean_abs_delta_apr": float((ex.apr[qualified] - base.apr[qualified]).abs().mean()),
          "max_abs_delta_apr": float((ex.apr[qualified] - base.apr[qualified]).abs().max()),
          "spearman_apr_vs_apr_exec": float(base.apr[qualified].rank().corr(ex.apr[qualified].rank()))}
    tab = pd.DataFrame({"batter_name": q.batter_name, "team": q.team, "pitches": q.pitches_seen, "sa": sa, "za": q.za_raw,
                        "apr": base.apr[qualified], "apr_exec": ex.apr[qualified], "e_runs_per_100_swings": 100 * e_full.reindex(qualified).fillna(0)})
    tab["rank_apr"] = tab.apr.rank(ascending=False, method="min").astype(int)
    tab["rank_apr_exec"] = tab.apr_exec.rank(ascending=False, method="min").astype(int)
    tab.sort_values("apr_exec", ascending=False).to_csv(OUT / f"v_execution_{y}.csv", float_format="%.4f")
    return {"V1": v1, "V2": v2, "sanity_max_abs_apr_vs_published": sanity}, tab


def main():
    res, tabs = {"seasons": {}}, {}
    for y in range(2019, 2027):
        res["seasons"][y], tabs[y] = season(y)
        print(y, json.dumps(res["seasons"][y]), flush=True)
    res["V2_seasons_delta_ge_0.10"] = sum(s["V2"]["delta"] >= .10 for s in res["seasons"].values())
    res["V2_verdict"] = res["V2_seasons_delta_ge_0.10"] >= 6
    # V3
    w = {y: woba(y) for y in range(2020, 2027)}
    frames = []
    for y in range(2019, 2026):
        t = tabs[y].join(w[y + 1], how="inner"); t = t[t.pa >= 150]
        frames.append(pd.DataFrame({"batter": t.index, "apr": t.apr - t.apr.mean(), "sa": t.sa - t.sa.mean(),
                                    "woba": t.woba - t.woba.mean(), "apr_exec": t.apr_exec - t.apr_exec.mean()}))
    d = pd.concat(frames, ignore_index=True)

    def coefs(x):
        X = np.column_stack([np.ones(len(x)), x.apr, x.sa])
        return np.linalg.lstsq(X, x.woba, rcond=None)[0]

    point = coefs(d); rng = np.random.default_rng(20261001); ids = d.batter.unique(); groups = d.groupby("batter").indices
    boots = []
    for _ in range(1000):
        pick = rng.choice(ids, len(ids), replace=True)
        boots.append(coefs(d.iloc[np.concatenate([groups[b] for b in pick])]))
    boots = np.array(boots)
    res["V3"] = {"pairs": len(d), "batters": len(ids), "coef_apr": float(point[1]), "coef_sa": float(point[2]),
                 "coef_sa_ci95": [float(np.percentile(boots[:, 2], 2.5)), float(np.percentile(boots[:, 2], 97.5))],
                 "coef_apr_ci95": [float(np.percentile(boots[:, 1], 2.5)), float(np.percentile(boots[:, 1], 97.5))],
                 "corr_next_woba": {"apr": float(d.apr.corr(d.woba)), "apr_exec": float(d.apr_exec.corr(d.woba)), "sa": float(d.sa.corr(d.woba))}}
    (OUT / "v_execution.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "seasons"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
