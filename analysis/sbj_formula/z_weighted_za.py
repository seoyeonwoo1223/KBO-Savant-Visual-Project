"""Z: ZA 존 밖 비용 가중 후보 비교 (gates.md Z).

python analysis/sbj_formula/z_weighted_za.py [외부 대조 CSV] -> results/z_weighted_za.json
외부 대조 CSV(season, cutoff, name, ext_zj)는 사용자 제공 타 사이트 화면값이라 저장소에 두지 않는다. 결과에는 집계치만 쓴다.
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
CANDS = ("Z0", "Z1", "Z2", "Z3", "R3")
YEARS = range(2019, 2027)


def load(y):
    ev = pq.read_table(ROOT / f"data/metrics/zone_awareness/{y}/pitches.parquet",
                       columns=["game_id", "game_date", "batter_id", "batter_name", "swing", "p_swing", "p_zone", "delta_v"]).to_pandas()
    ev["batter_id"] = ev.batter_id.astype(str); ev["date"] = ev.game_date.astype(str).str[:10]
    ev["j"] = (ev.swing - ev.p_swing) * (2 * ev.p_zone - 1); ev["out"] = ev.p_zone < .5
    return ev


def ratio(ev):
    return float(-ev.delta_v[ev.out].mean() / ev.delta_v[~ev.out].mean())


def weights(ev, pooled):
    w = {"Z0": np.ones(len(ev)), "Z1": np.where(ev.out, ratio(ev), 1.0), "Z2": np.where(ev.out, pooled, 1.0),
         "R3": np.where(ev.out, 3.0, 1.0)}
    bins = np.minimum((ev.p_zone * 10).astype(int), 9)
    w["Z3"] = bins.map(ev.delta_v.groupby(bins).mean().abs()).to_numpy()
    return {k: v / v.mean() for k, v in w.items()}


def scores(ev, w, min_n):
    n = ev.groupby("batter_id").size(); keep = n.index[n >= min_n]
    return pd.DataFrame({c: (100 * w[c] * ev.j).groupby(ev.batter_id).mean() for c in CANDS}).loc[keep]


def main():
    evs = {y: load(y) for y in YEARS}
    ratios = {y: ratio(evs[y]) for y in YEARS}; pooled = float(np.mean(list(ratios.values())))
    res = {"ratio_by_season": ratios, "pooled_ratio": pooled, "seasons": {}}
    full, rel = {}, {c: {} for c in CANDS}
    for y in YEARS:
        ev = evs[y]; w = weights(ev, pooled)
        t = scores(ev, w, 300); t["sa"] = 100 * (ev.swing - ev.p_swing).groupby(ev.batter_id).mean()
        full[y] = t
        g = ev.game_id.astype("category").cat.codes
        a, b = scores(ev[g % 2 == 0], {k: v[(g % 2 == 0).to_numpy()] for k, v in w.items()}, 150), \
            scores(ev[g % 2 == 1], {k: v[(g % 2 == 1).to_numpy()] for k, v in w.items()}, 150)
        ids = a.index.intersection(b.index)
        for c in CANDS:
            r = a.loc[ids, c].corr(b.loc[ids, c]); rel[c][y] = float(2 * r / (1 + r))
        res["seasons"][y] = {"league_mean": {c: float(100 * (w[c] * ev.j).mean()) for c in CANDS},
                             "spearman_sa": {c: float(t[c].rank().corr(t.sa.rank())) for c in CANDS},
                             "spearman_vs_Z0": {c: float(t[c].rank().corr(t.Z0.rank())) for c in CANDS}}
        print(y, "ratio", round(ratios[y], 2), {c: round(rel[c][y], 3) for c in CANDS}, flush=True)
    # 외부 대조
    ext_res = None
    if len(sys.argv) > 1:
        ext = pd.read_csv(sys.argv[1]); ext.loc[ext.cutoff == "2024-08-19", "cutoff"] = "2024-08-18"
        rows = []
        for (y, cut), grp in ext.groupby(["season", "cutoff"]):
            ev = evs[int(y)]; w = weights(ev, pooled)
            m = (ev.date <= (ev.date.max() if cut == "full" else cut)).to_numpy()
            e = ev[m]; ww = {k: v[m] for k, v in w.items()}
            pa = pd.DataFrame([r for r in load_rows(ROOT, "pitches", int(y), columns=["batter_id", "game_id", "is_pa_terminal"]) if r["is_pa_terminal"]])
            pa["batter_id"] = pa.batter_id.astype(str)
            pa = pa[pd.to_datetime(pa.game_id.str[:8]) <= pd.Timestamp(e.date.max())]
            npa = pa.groupby("batter_id").size(); ref = npa.index[npa >= e.game_id.nunique() * 2 / 10]
            s = scores(e, ww, 1); names = e.groupby("batter_id").batter_name.first()
            for _, x in grp.iterrows():
                ids = names.index[names == x["name"]]; i = max(ids, key=lambda k: npa.get(k, 0))
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
        v = {"ZG1_reliability": float(np.mean(list(rel[c].values()))), "ZG1_by_season": rel[c],
             "ZG2_max_abs_sa": max(abs(res["seasons"][y]["spearman_sa"][c]) for y in YEARS),
             "ZG3_max_abs_league_mean": max(abs(res["seasons"][y]["league_mean"][c]) for y in YEARS),
             "ZG5_next_bb_pct": float(d[c].corr(d.bb_pct)), "next_woba": float(d[c].corr(d.woba)),
             "ZG6_x4": float(coef(d, c)), "ZG6_x4_ci95": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
             "ZG6_year_to_year": float(pd.concat(yy[c]).corr().iloc[0, 1])}
        res["candidates"][c] = v
    z0 = res["candidates"]["Z0"]
    for c in ("Z1", "Z2", "Z3"):
        v = res["candidates"][c]
        v["pass"] = {"ZG1": v["ZG1_reliability"] >= .75, "ZG2": v["ZG2_max_abs_sa"] <= .30, "ZG3": v["ZG3_max_abs_league_mean"] <= .10,
                     "ZG4": ext_res is not None and ext_res["spearman"][c] > ext_res["spearman"]["Z0"], "ZG5": v["ZG5_next_bb_pct"] >= z0["ZG5_next_bb_pct"]}
        v["all_pass"] = all(v["pass"].values())
    rec = "Z1" if res["candidates"]["Z1"]["all_pass"] else max([c for c in ("Z2", "Z3") if res["candidates"][c]["all_pass"]],
                                                              key=lambda c: res["candidates"][c]["ZG1_reliability"], default=None)
    res["recommended"] = rec
    (OUT / "z_weighted_za.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"ratios": ratios, "external": ext_res, "candidates": {c: {k: v for k, v in res["candidates"][c].items() if k != "ZG1_by_season"} for c in CANDS},
                      "recommended": rec}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
