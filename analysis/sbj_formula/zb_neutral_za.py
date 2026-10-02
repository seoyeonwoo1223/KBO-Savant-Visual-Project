"""Z-b: 공격성 중립 + 나눈 비용 가중 ZA (gates.md Z-b).

python analysis/sbj_formula/zb_neutral_za.py [--recenter] [외부 대조 CSV] -> results/zb_neutral_za[_recenter].json, results/zb_neutral_za[_recenter]_<Y>.csv
--recenter: Z-c. 표본 리그 투구 평균을 빼 0에 맞춘다.
외부 대조 CSV는 사용자 제공 타 사이트 화면값이라 저장소에 두지 않는다. 결과에는 집계치만 쓴다.
읽기 전용. za7.6 투구 근거와 curated 타석 결과만 읽는다.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).parent))
from x_compare import outcomes, pct  # noqa: E402
from visualbaseball.curated import load_rows  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("results")
CANDS = ("Z0", "N0", "N1", "N2", "N3", "N4")
CELLS = {"Z0": 0, "N0": 1, "N1": 2, "N3": 5, "N2": 6, "N4": 15}
YEARS = range(2019, 2027)
RECENTER = "--recenter" in sys.argv
if RECENTER:
    sys.argv.remove("--recenter")
TAG = "_recenter" if RECENTER else ""
POOLED_RATIO = 1.67  # Z 결과의 2019–2026 평균 비용 비율


def load(y):
    ev = pq.read_table(ROOT / f"data/metrics/zone_awareness/{y}/pitches.parquet",
                       columns=["game_id", "game_date", "batter_id", "batter_name", "swing", "p_swing", "p_zone", "delta_v",
                                "region", "strikes_before"]).to_pandas()
    ev["batter_id"] = ev.batter_id.astype(str); ev["date"] = ev.game_date.astype(str).str[:10]
    ev["side"] = np.where(ev.p_zone >= .5, "in", "out")
    return ev


def weights(ev):
    cell_w = lambda keys: ev.groupby(keys).delta_v.transform("mean").abs().to_numpy()
    w = {"Z0": np.ones(len(ev)), "N0": np.ones(len(ev)), "N1": np.where(ev.side == "out", POOLED_RATIO, 1.0),
         "N2": cell_w(["side", "strikes_before"]), "N3": cell_w(["region"]), "N4": cell_w(["region", "strikes_before"])}
    return {k: v / v.mean() for k, v in w.items()}


def scores(ev, w, min_n):
    r = (ev.swing - ev.p_swing).to_numpy(); z = (2 * ev.p_zone - 1).to_numpy()
    m = pd.Series(r).groupby(ev.batter_id.to_numpy()).transform("mean").to_numpy()
    n = ev.groupby("batter_id").size(); keep = n.index[n >= min_n]
    cols = {c: (100 * w[c] * (r if c == "Z0" else r - m) * z) for c in CANDS}
    if RECENTER:
        cols = {c: v - v.mean() for c, v in cols.items()}
    return pd.DataFrame({c: pd.Series(v).groupby(ev.batter_id.to_numpy()).mean() for c, v in cols.items()}).loc[keep], cols


def main():
    evs = {y: load(y) for y in YEARS}
    res = {"seasons": {}}; full, rel = {}, {c: {} for c in CANDS}
    for y in YEARS:
        ev = evs[y]; w = weights(ev)
        t, cols = scores(ev, w, 300); t["sa"] = 100 * (ev.swing - ev.p_swing).groupby(ev.batter_id).mean()
        t["batter_name"] = ev.groupby("batter_id").batter_name.first()
        full[y] = t
        g = (ev.game_id.astype("category").cat.codes % 2).to_numpy()
        a = scores(ev[g == 0], {k: v[g == 0] for k, v in w.items()}, 150)[0]
        b = scores(ev[g == 1], {k: v[g == 1] for k, v in w.items()}, 150)[0]
        ids = a.index.intersection(b.index)
        for c in CANDS:
            rr = a.loc[ids, c].corr(b.loc[ids, c]); rel[c][y] = float(2 * rr / (1 + rr))
        cell = {k: ev.assign(w=w[k]).groupby(keys).w.first().round(3).to_dict() for k, keys in (("N2", ["side", "strikes_before"]), ("N3", ["region"]), ("N4", ["region", "strikes_before"]))}
        res["seasons"][y] = {"league_mean": {c: float(np.mean(cols[c])) for c in CANDS},
                             "spearman_sa": {c: float(t[c].rank().corr(t.sa.rank())) for c in CANDS},
                             "spearman_vs_Z0": {c: float(t[c].rank().corr(t.Z0.rank())) for c in CANDS},
                             "weights": {k: {"|".join(map(str, kk if isinstance(kk, tuple) else (kk,))): v for kk, v in d.items()} for k, d in cell.items()}}
        t.sort_values(CANDS[-1], ascending=False).to_csv(OUT / f"zb_neutral_za{TAG}_{y}.csv", float_format="%.4f")
        print(y, {c: round(rel[c][y], 3) for c in CANDS}, {c: round(res["seasons"][y]["spearman_sa"][c], 2) for c in CANDS}, flush=True)
    ext_res = None
    if len(sys.argv) > 1:
        ext = pd.read_csv(sys.argv[1]); ext.loc[ext.cutoff == "2024-08-19", "cutoff"] = "2024-08-18"
        rows = []
        for (y, cut), grp in ext.groupby(["season", "cutoff"]):
            ev = evs[int(y)]; w = weights(ev)
            mask = (ev.date <= (ev.date.max() if cut == "full" else cut)).to_numpy()
            e = ev[mask]
            pa = pd.DataFrame([r for r in load_rows(ROOT, "pitches", int(y), columns=["batter_id", "game_id", "is_pa_terminal"]) if r["is_pa_terminal"]])
            pa["batter_id"] = pa.batter_id.astype(str); pa = pa[pd.to_datetime(pa.game_id.str[:8]) <= pd.Timestamp(e.date.max())]
            npa = pa.groupby("batter_id").size(); ref = npa.index[npa >= e.game_id.nunique() * 2 / 10]
            s = scores(e, {k: v[mask] for k, v in w.items()}, 1)[0]; names = e.groupby("batter_id").batter_name.first()
            for _, x in grp.iterrows():
                i = max(names.index[names == x["name"]], key=lambda k: npa.get(k, 0))
                rows.append({"ext": x.ext_zj, **{c: float(pct(s.loc[[i], c], s.loc[s.index.intersection(ref), c]).iloc[0]) for c in CANDS}})
        d = pd.DataFrame(rows)
        ext_res = {"points": len(d), "spearman": {c: float(d.ext.corr(d[c], method="spearman")) for c in CANDS},
                   "mae_percentile": {c: float((d.ext - d[c]).abs().mean()) for c in CANDS}}
    res["external"] = ext_res
    out = {y: outcomes(y) for y in YEARS}; frames, yy = [], {c: [] for c in CANDS}
    for y in range(2019, 2026):
        t = full[y].join(out[y][["iso"]], how="inner").join(out[y + 1][["pa", "bb_pct", "woba"]], how="inner")
        t = t[t.pa >= 150].dropna(subset=["iso"])
        frames.append(pd.DataFrame({"b": t.index, **{c: t[c] - t[c].mean() for c in list(CANDS) + ["iso", "bb_pct", "woba"]}}))
        ids = full[y].index.intersection(full[y + 1].index)
        for c in CANDS:
            yy[c].append(pd.DataFrame({"a": full[y].loc[ids, c], "b": full[y + 1].loc[ids, c]}))
    d = pd.concat(frames, ignore_index=True)
    rng = np.random.default_rng(20261001); bats = d.b.unique(); gi = d.groupby("b").indices
    picks = [np.concatenate([gi[b] for b in rng.choice(bats, len(bats))]) for _ in range(1000)]

    def coef(x, c):
        X = np.column_stack([np.ones(len(x)), (x[c] - x[c].mean()) / x[c].std(), (x.iso - x.iso.mean()) / x.iso.std()])
        return np.linalg.lstsq(X, (x.woba - x.woba.mean()) / x.woba.std(), rcond=None)[0][1]

    res["candidates"] = {}
    for c in CANDS:
        boots = np.array([coef(d.iloc[p], c) for p in picks])
        res["candidates"][c] = {"ZG1_reliability": float(np.mean(list(rel[c].values()))), "ZG1_by_season": rel[c],
                                "ZG2_max_abs_sa": max(abs(res["seasons"][y]["spearman_sa"][c]) for y in YEARS),
                                "ZG3_max_abs_league_mean": max(abs(res["seasons"][y]["league_mean"][c]) for y in YEARS),
                                "ZG5_next_bb_pct": float(d[c].corr(d.bb_pct)), "next_woba": float(d[c].corr(d.woba)),
                                "ZG6_x4": float(coef(d, c)), "ZG6_x4_ci95": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
                                "ZG6_year_to_year": float(pd.concat(yy[c]).corr().iloc[0, 1])}
    z0 = res["candidates"]["Z0"]
    for c in CANDS[1:]:
        v = res["candidates"][c]
        v["pass"] = {"ZG1": v["ZG1_reliability"] >= .75, "ZG2": v["ZG2_max_abs_sa"] <= .30, "ZG3": v["ZG3_max_abs_league_mean"] <= .10,
                     "ZG4": ext_res is not None and ext_res["spearman"][c] > ext_res["spearman"]["Z0"], "ZG5": v["ZG5_next_bb_pct"] >= z0["ZG5_next_bb_pct"]}
        v["all_pass"] = all(v["pass"].values())
    passing = [c for c in CANDS[1:] if res["candidates"][c]["all_pass"]]
    rec = None
    if passing:
        best = max(passing, key=lambda c: res["candidates"][c]["ZG6_x4"])
        close = [c for c in passing if res["candidates"][c]["ZG6_x4"] >= res["candidates"][best]["ZG6_x4_ci95"][0]]
        rec = min(close, key=lambda c: CELLS[c])
    res["passing"] = passing; res["recommended"] = rec
    (OUT / f"zb_neutral_za{TAG}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for c in CANDS:
        v = res["candidates"][c]
        print(f"{c} rel {v['ZG1_reliability']:.3f} |SA| {v['ZG2_max_abs_sa']:.2f} mean {v['ZG3_max_abs_league_mean']:.3f} "
              f"ext {ext_res['spearman'][c] if ext_res else float('nan'):.2f}/{ext_res['mae_percentile'][c] if ext_res else float('nan'):.1f} "
              f"BB {v['ZG5_next_bb_pct']:.3f} wOBA {v['next_woba']:.3f} X4 {v['ZG6_x4']:+.3f} [{v['ZG6_x4_ci95'][0]:+.3f},{v['ZG6_x4_ci95'][1]:+.3f}] y2y {v['ZG6_year_to_year']:.2f} pass {v.get('pass')}")
    print("passing", passing, "recommended", rec)


if __name__ == "__main__":
    main()
