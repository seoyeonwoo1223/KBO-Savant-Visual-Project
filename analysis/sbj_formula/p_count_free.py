"""P: p_swing에서 카운트를 뺐을 때 APR이 어떻게 바뀌는가 + 2스트라이크 스윙 손익 (gates.md P).

python analysis/sbj_formula/p_count_free.py fit 2019 2020 ...   # 시즌별 p_swing 재적합 -> /tmp/sbj_formula_cache/p_count_<Y>.npz
python analysis/sbj_formula/p_count_free.py analyze             # results/p_count_free.json, results/p_count_free_<Y>.csv
읽기 전용. za7.6 투구 근거, 운영 load_rows 행(캐시), 공개 leaderboard, curated 타석 결과만 읽는다.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import GroupKFold

sys.path.insert(0, str(Path(__file__).parent))
import sbj_exp as E  # noqa: E402
from v_execution import cluster_mean  # noqa: E402
from x_compare import outcomes  # noqa: E402
from visualbaseball import plate_decision_v1 as old  # noqa: E402
from visualbaseball import zone_decision as zd  # noqa: E402

ROOT = E.ROOT
OUT = Path(__file__).with_name("results")
COUNT = ("balls_before", "strikes_before")
VARIANTS = {"count": zd.NUMERIC, "nocount": tuple(f for f in zd.NUMERIC if f not in COUNT)}
CANDS = ("A", "A_nc", "B", "B_nc")
REGIONS = zd.REGIONS
EVENTS = ("Whiff", "Foul", "InPlay", "Ball", "CalledStrike")


def classifier(numeric):
    k = len(numeric)
    return old._classifier(k).set_params(categorical_features=list(range(k, k + len(zd.PSWING_CATEGORICAL))), early_stopping=False)


def iso(x, y):
    return IsotonicRegression(out_of_bounds="clip", y_min=1e-6, y_max=1 - 1e-6).fit(x, y)


def fit_block(train, test, numeric, train_in, test_in):
    sa, sb = zd.encode(train, test, zd.PSWING_CATEGORICAL, numeric=numeric)
    y = np.array([r["decision_type"] == "Swing" for r in train], dtype=int)
    proba = lambda m, x: m.predict_proba(x)[:, list(m.classes_).index(1)]
    raw = proba(zd.fit_model(classifier(numeric), sa, y), sb)
    groups = np.array([r["game_id"] for r in train]); oof = np.empty(len(train))
    for fit, held in GroupKFold(3).split(sa, y, groups):
        oof[held] = proba(zd.fit_model(classifier(numeric), sa[fit], y[fit]), sa[held])
    p = iso(oof, y).predict(raw)
    for side in (True, False):
        m, t = train_in == side, test_in == side
        if len(set(y[m])) == 2 and t.any():
            p[t] = iso(oof[m], y[m]).predict(raw[t])
    return p


def fit(y):
    rows = E.rows_for(y); ordered, fold, blocks = E.ordered_folds(rows)
    ev = pq.read_table(ROOT / f"data/metrics/zone_awareness/{y}/pitches.parquet", columns=["game_id", "event", "p_zone", "fold"]).to_pandas()
    assert len(ev) == len(ordered) and (ev.game_id.to_numpy() == np.array([r["game_id"] for r in ordered])).all()
    assert (ev.event.to_numpy() == np.array([r["event"] for r in ordered])).all() and (ev.fold.to_numpy() == fold).all()
    pos = {id(r): i for i, r in enumerate(ordered)}; inz = ev.p_zone.to_numpy() >= .5
    out = {k: np.full(len(ordered), np.nan) for k in VARIANTS}
    t0 = time.time()
    for f, held in enumerate(blocks):
        train = [r for r in rows if r["game_id"][:8] not in held]
        idx = np.flatnonzero(fold == f); test = [ordered[i] for i in idx]
        tr_in = inz[[pos[id(r)] for r in train]]
        for k, numeric in VARIANTS.items():
            out[k][idx] = fit_block(train, test, numeric, tr_in, inz[idx])
        print(y, "block", f, round(time.time() - t0), "s", flush=True)
    np.savez(E.CACHE / f"p_count_{y}.npz", **out)


def apr(ev, col, min_q):
    t = cluster_mean(ev[col], ev.batter_id, ev.game_id)
    players = [{"batter_id": b, "pitches_seen": int(t.n[b]), "qualified_300": bool(t.n[b] >= min_q),
                "jdv_per_100": float(100 * t["mean"][b]), "jdv_se": float(100 * t.se[b])} for b in t.index]
    zd.add_apr(players, 100 * float(ev.dv.mean()), 100 * float(ev[col].mean()))
    d = pd.DataFrame(players).set_index("batter_id")
    return d.apr, d.apr_percentile


def candidates(ev, min_q):
    ev = ev.copy()
    for tag, p in (("", "p_c"), ("_nc", "p_nc")):
        r = ev.swing - ev[p]
        ev["A" + tag] = 2 * r * ev.delta_v
        ev["B" + tag] = 2 * (r - r.groupby(ev.batter_id).transform("mean")) * ev.delta_v
    n = ev.groupby("batter_id").size(); q = n.index[n >= min_q]
    out = pd.DataFrame({"n": n, "sa": 100 * (ev.swing - ev.p_swing).groupby(ev.batter_id).mean(),
                        "two_strike_share": (ev.strikes_before == 2).groupby(ev.batter_id).mean()})
    for c in CANDS:
        out[c], out[c + "_pct"] = apr(ev, c, min_q)
    return out.loc[q]


def cell_table(ev):
    rows = []
    for (s, reg), g in ev.groupby(["strikes_before", "region"]):
        dv = 100 * g.delta_v; m = dv.mean(); dev = (dv - m).groupby(g.game_id).sum()
        se = float(np.sqrt((dev ** 2).sum()) / len(g))
        sw = g[g.swing == 1]
        rows.append({"strikes": int(s), "region": reg, "n": len(g), "swing_pct": 100 * g.swing.mean(),
                     "lg_p_nc_pct": 100 * g.p_nc.mean(), "mean_dv": m, "ci_lo": m - 1.96 * se, "ci_hi": m + 1.96 * se,
                     "share_dv_pos": float((g.delta_v > 0).mean()), "mean_dv_swung": float(100 * sw.delta_v.mean()) if len(sw) else None,
                     **{f"p_{e}": float(100 * g[f"p_{e}"].mean()) for e in EVENTS},
                     "verdict": "loss" if m + 1.96 * se < 0 else "gain" if m - 1.96 * se > 0 else "uncertain"})
    return pd.DataFrame(rows)


def analyze():
    res = {"seasons": {}}; full, rel = {}, {c: {} for c in CANDS}; cells = []
    for y in range(2019, 2027):
        cols = ["game_id", "batter_id", "swing", "p_swing", "delta_v", "dv", "region", "strikes_before"] + [f"p_{e}" for e in EVENTS]
        ev = pq.read_table(ROOT / f"data/metrics/zone_awareness/{y}/pitches.parquet", columns=cols).to_pandas()
        ev["batter_id"] = ev.batter_id.astype(str)
        z = np.load(E.CACHE / f"p_count_{y}.npz"); ev["p_c"], ev["p_nc"] = z["count"], z["nocount"]
        board = pd.DataFrame(json.loads((ROOT / f"web/data/zone_awareness/{y}/leaderboard.json").read_text(encoding="utf-8"))["players"])
        board = board.assign(batter_id=board.batter_id.astype(str)).set_index("batter_id")
        full[y] = t = candidates(ev, 300)
        h0 = float(t.A.rank().corr(board.apr[t.index].rank()))
        y_ = ev.swing.to_numpy()
        la, lb = E.bernoulli_loss(y_, ev.p_c.to_numpy()), E.bernoulli_loss(y_, ev.p_nc.to_numpy())
        d_ll, z_ll = E.cluster_z(la, lb, ev.game_id.to_numpy())
        brier = {k: float(np.mean((y_ - ev[k]) ** 2)) for k in ("p_c", "p_nc")}
        by_strike = {int(s): {"swing_pct": float(100 * g.swing.mean()), "p_c_pct": float(100 * g.p_c.mean()), "p_nc_pct": float(100 * g.p_nc.mean()),
                              "league_A_per_100": float(100 * (2 * (g.swing - g.p_c) * g.delta_v).mean()),
                              "league_A_nc_per_100": float(100 * (2 * (g.swing - g.p_nc) * g.delta_v).mean())}
                     for s, g in ev.groupby("strikes_before")}
        ct = cell_table(ev); ct.insert(0, "season", y); cells.append(ct)
        games = ev.game_id.astype("category").cat.codes
        a, b = candidates(ev[games % 2 == 0], 150), candidates(ev[games % 2 == 1], 150)
        ids = a.index.intersection(b.index)
        for c in CANDS:
            r = a.loc[ids, c].corr(b.loc[ids, c]); rel[c][y] = float(2 * r / (1 + r))
        res["seasons"][y] = {
            "H0_spearman_harness_A_vs_published": h0, "H0_pass": h0 >= .98,
            "P1": {"logloss_count": float(la.mean()), "logloss_nocount": float(lb.mean()), "delta": d_ll, "cluster_z": z_ll, "brier": brier},
            "by_strike": by_strike,
            "P2_spearman_two_strike_share": {c: float(t[c].rank().corr(t.two_strike_share.rank())) for c in CANDS},
            "P6_spearman_sa": {c: float(t[c].rank().corr(t.sa.rank())) for c in CANDS},
            "rank_corr_vs_count": {"A": float(t.A.rank().corr(t.A_nc.rank())), "B": float(t.B.rank().corr(t.B_nc.rank()))},
            "mean_abs_pct_change": {"A": float((t.A_nc_pct - t.A_pct).abs().mean()), "B": float((t.B_nc_pct - t.B_pct).abs().mean())},
        }
        if "50167" in t.index:
            res["seasons"][y]["lee_juhyung"] = {c: [float(t.loc["50167", c]), float(t.loc["50167", c + "_pct"])] for c in CANDS}
        t.join(board[["batter_name", "team"]]).sort_values("A_nc", ascending=False).to_csv(OUT / f"p_count_free_{y}.csv", float_format="%.4f")
        print(y, "H0", round(h0, 3), "P1", round(d_ll, 5), round(z_ll, 1), "rel", {c: round(rel[c][y], 2) for c in CANDS}, flush=True)
    cells = pd.concat(cells); cells.to_csv(OUT / "p_count_free_cells.csv", index=False, float_format="%.4f")
    verdict = cells.groupby(["strikes", "region"]).verdict.agg(lambda v: v.value_counts().to_dict())
    res["D_verdicts"] = {f"{s}|{reg}": v for (s, reg), v in verdict.items()}
    res["D_conclusion"] = {k: next((lab for lab, n in v.items() if n >= 6), "none") for k, v in res["D_verdicts"].items()}
    res["D_mean_over_seasons"] = cells.groupby(["strikes", "region"])[["swing_pct", "mean_dv", "share_dv_pos", "mean_dv_swung", "p_Whiff", "p_Foul", "p_InPlay", "p_Ball", "p_CalledStrike"]].mean().round(3).reset_index().to_dict("records")
    out = {y: outcomes(y) for y in range(2019, 2027)}; frames = []
    for y in range(2019, 2026):
        t = full[y].join(out[y][["iso"]], how="inner").join(out[y + 1][["pa", "woba"]], how="inner")
        t = t[t.pa >= 150].dropna(subset=["iso"])
        frames.append(pd.DataFrame({"batter": t.index, **{c: t[c] - t[c].mean() for c in list(CANDS) + ["iso", "woba"]}}))
    d = pd.concat(frames, ignore_index=True)
    rng = np.random.default_rng(20261001); bats = d.batter.unique(); groups = d.groupby("batter").indices
    picks = [np.concatenate([groups[b] for b in rng.choice(bats, len(bats), replace=True)]) for _ in range(1000)]

    def coef(x, c):
        X = np.column_stack([np.ones(len(x)), (x[c] - x[c].mean()) / x[c].std(), (x.iso - x.iso.mean()) / x.iso.std()])
        return np.linalg.lstsq(X, (x.woba - x.woba.mean()) / x.woba.std(), rcond=None)[0][1]

    boots = {c: np.array([coef(d.iloc[p], c) for p in picks]) for c in CANDS}
    seasons_ok = [y for y in res["seasons"] if res["seasons"][y]["H0_pass"]]
    res["H0_failed_seasons"] = [y for y in res["seasons"] if y not in seasons_ok]
    res["pairs"] = len(d); res["candidates"] = {}
    for c in CANDS:
        base = c.replace("_nc", "")
        p2 = max(abs(res["seasons"][y]["P2_spearman_two_strike_share"][c]) for y in seasons_ok)
        p3 = float(np.mean([rel[c][y] for y in seasons_ok]))
        ci = [float(np.percentile(boots[c], 2.5)), float(np.percentile(boots[c], 97.5))]
        diff = boots[c] - boots[base]
        res["candidates"][c] = {"P2_max_abs": p2, "P2_pass": p2 <= .30, "P3_reliability": p3, "P3_pass": p3 >= .60,
                                "P4_coef": float(coef(d, c)), "P4_ci95": ci, "P4_pass": ci[0] > 0,
                                "P6_max_abs_sa": max(abs(res["seasons"][y]["P6_spearman_sa"][c]) for y in seasons_ok)}
        if c != base:
            dci = [float(np.percentile(diff, 2.5)), float(np.percentile(diff, 97.5))]
            res["candidates"][c].update({"P5_diff_vs_count": float(coef(d, c) - coef(d, base)), "P5_ci95": dci, "P5_pass": dci[0] > 0})
            res["candidates"][c]["recommend_drop_count"] = all(res["candidates"][c][k] for k in ("P2_pass", "P3_pass", "P4_pass", "P5_pass"))
    (OUT / "p_count_free.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k not in ("seasons", "D_mean_over_seasons")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    if sys.argv[1] == "fit":
        for y in map(int, sys.argv[2:]):
            fit(y)
    else:
        analyze()
