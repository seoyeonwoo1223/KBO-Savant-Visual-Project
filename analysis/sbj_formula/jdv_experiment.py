"""판단 DV(JDV) 실험 (gates.md J). python analysis/sbj_formula/jdv_experiment.py

za7.3 재빌드 투구 근거(data/metrics/zone_awareness/<Y>/pitches.parquet)와 curated 타석 결과만 읽는다.
결과: results/jdv.json, results/jdv_player_changes_<Y>.csv
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from visualbaseball.curated import load_rows  # noqa: E402
from visualbaseball.zone_decision import MODEL_VERSION  # noqa: E402

OUT = Path(__file__).with_name("results")
SEASONS = range(2019, 2027)
QUAL = 300
METRICS = ("dv", "jdv", "expected", "judgment")


def evidence(y):
    report = json.loads((ROOT / f"data/metrics/zone_awareness/{y}/report.json").read_text(encoding="utf-8"))
    assert report["model_version"] == MODEL_VERSION, (y, report["model_version"])
    df = pq.read_table(ROOT / f"data/metrics/zone_awareness/{y}/pitches.parquet",
                       columns=["game_id", "batter_id", "batter_name", "swing", "p_swing", "delta_v", "dv", "judgment", "fold"]).to_pandas()
    df["batter_id"] = df.batter_id.astype(str)
    df["jdv"] = 2 * (df.swing - df.p_swing) * df.delta_v
    df["expected"] = (2 * df.p_swing - 1) * df.delta_v
    assert np.allclose(df.dv, df.jdv + df.expected)
    return df


def per_batter(df, key):
    g = df.groupby("batter_id"); n = g.size(); m = g[key].mean()
    dev = df[key] - df.batter_id.map(m)
    se = np.sqrt((dev.groupby([df.batter_id, df.game_id]).sum() ** 2).groupby(level=0).sum()) / n
    return pd.DataFrame({"n": n, "score": 100 * m, "se": 100 * se})


def reliability(t):
    return 1 - (t.se ** 2).mean() / t.score.var(ddof=1)


def plus(s):
    return 100 + 15 * (s - s.mean()) / s.std(ddof=0)


_PA_TYPE = {}


def pa_type_map():
    """pa_result → pa_type 대응표. pa_type이 있는 시즌에서 만든다(2019–2021·2025–2026에서 132종, 모호한 대응 0).

    2022–2024 curated에는 pa_type이 없고 pa_result만 있다. 처음 실행은 이를 몰라 세 시즌의 결과 비율이
    모두 0으로 들어갔다(README J절). 대응표에 없는 결과(2022–2024 합계 5타석: 유희·일삼·중IFO·중파)는 이름상
    모두 아웃이므로 out으로 둔다.
    """
    if not _PA_TYPE:
        for y in SEASONS:
            for r in load_rows(ROOT, "pitches", y, columns=["is_pa_terminal", "pa_type", "pa_result"]):
                if r["is_pa_terminal"] and r["pa_type"]:
                    _PA_TYPE.setdefault(r["pa_result"], r["pa_type"])
    return _PA_TYPE


def outcomes(y):
    rows = load_rows(ROOT, "pitches", y, columns=["batter_id", "is_pa_terminal", "pa_type", "pa_result"])
    t = pd.DataFrame([r for r in rows if r["is_pa_terminal"]])
    t["batter_id"] = t.batter_id.astype(str)
    mapping = pa_type_map()
    missing = t.pa_type.isna()
    t.loc[missing, "pa_type"] = t.loc[missing, "pa_result"].map(lambda v: mapping.get(v, "out"))
    t["hbp"] = t.pa_result.eq("사구")
    t["bb"] = t.pa_type.eq("bb") & ~t.hbp
    t["k"] = t.pa_type.eq("k"); t["hr"] = t.pa_type.eq("hr")
    t["on"] = t.pa_type.isin(["hit", "hr", "bb"])
    g = t.groupby("batter_id")
    return pd.DataFrame({"pa": g.size(), "bb_pct": g.bb.mean(), "k_pct": g.k.mean(), "obp": g.on.mean(), "hr_pct": g.hr.mean()})


def main():
    res = {"model_version": MODEL_VERSION, "seasons": {}}
    tables, outs = {}, {}
    for y in SEASONS:
        df = evidence(y)
        per = {k: per_batter(df, k) for k in METRICS}
        q = per["jdv"].index[per["jdv"].n >= QUAL]
        tab = pd.DataFrame({k: per[k].score[q] for k in METRICS})
        tables[y] = tab; outs[y] = outcomes(y)
        # J2: 블록 쌍 관측 상관 / 기대 상관
        pairs = []
        for a, b in ((0, 1), (1, 2), (0, 2)):
            ta, tb = per_batter(df[df.fold == a], "jdv"), per_batter(df[df.fold == b], "jdv")
            ids = ta.index[ta.n >= 150].intersection(tb.index[tb.n >= 150])
            r = float(np.corrcoef(ta.score[ids], tb.score[ids])[0, 1])
            ra, rb = reliability(ta.loc[ids]), reliability(tb.loc[ids])
            exp = float(np.sqrt(max(ra, 0) * max(rb, 0)))
            pairs.append({"blocks": [a + 1, b + 1], "batters": len(ids), "r": r, "expected_r": exp, "ratio": r / exp if exp > 0 else None})
        dvp, jdvp = plus(tab.dv), plus(tab.jdv)
        rank_d, rank_j = dvp.rank(ascending=False, method="min"), jdvp.rank(ascending=False, method="min")
        shift = (rank_d - rank_j).abs()
        names = df.groupby("batter_id").batter_name.first()
        pd.DataFrame({"batter_id": q, "batter_name": names[q].values, "dv_per_100": tab.dv.values, "jdv_per_100": tab.jdv.values,
                      "expected_per_100": tab.expected.values, "dv_plus": dvp.values, "jdv_plus": jdvp.values,
                      "rank_dv_plus": rank_d.values, "rank_jdv_plus": rank_j.values}).sort_values("rank_dv_plus").to_csv(
            OUT / f"jdv_player_changes_{y}.csv", index=False, float_format="%.4f")
        rel = {k: float(reliability(per[k].loc[q])) for k in METRICS}
        ratio = float(np.mean([p["ratio"] for p in pairs]))
        rho = float(tab.jdv.rank().corr(tab.expected.rank()))
        res["seasons"][y] = {
            "qualified": len(q), "sd": {k: float(tab[k].std()) for k in METRICS}, "reliability": rel,
            "block_pairs_jdv": pairs,
            "spearman": {"jdv_expected": rho, "dv_expected": float(tab.dv.rank().corr(tab.expected.rank())),
                         "jdv_dv": float(tab.jdv.rank().corr(tab.dv.rank())), "jdv_sbj": float(tab.jdv.rank().corr(tab.judgment.rank())),
                         "dv_sbj": float(tab.dv.rank().corr(tab.judgment.rank()))},
            "J6": {"spearman_plus": float(dvp.rank().corr(jdvp.rank())), "max_rank_shift": int(shift.max()),
                   "moved_5_or_more": int((shift >= 5).sum()), "mean_abs_delta_plus": float((jdvp - dvp).abs().mean()),
                   "max_abs_delta_plus": float((jdvp - dvp).abs().max())},
            "gates": {"J1": {"reliability": rel["jdv"], "pass": rel["jdv"] >= .60},
                      "J2": {"mean_ratio": ratio, "pass": ratio >= .80},
                      "J3": {"spearman": rho, "pass": abs(rho) <= .30}},
        }
        res["seasons"][y]["gates"]["pass"] = all(g["pass"] for g in res["seasons"][y]["gates"].values())
        print(y, json.dumps(res["seasons"][y]["gates"]), flush=True)
    # J4 시즌 간 상관, J5 외부 타당성
    j4 = {k: [] for k in METRICS}; same, nxt = [], []
    for y in SEASONS:
        o = outs[y]; same.append(tables[y].join(o, how="inner"))
        if y + 1 in tables:
            ids = tables[y].index.intersection(tables[y + 1].index)
            for k in METRICS:
                j4[k].append(pd.DataFrame({"a": tables[y][k][ids], "b": tables[y + 1][k][ids]}))
            nxt.append(tables[y].loc[ids].join(outs[y + 1].loc[outs[y + 1].index.intersection(ids)], how="inner"))
    res["J4_year_to_year"] = {k: {"pairs": int(sum(len(x) for x in v)), "r": float(pd.concat(v).corr().iloc[0, 1])} for k, v in j4.items()}
    cols = ["bb_pct", "k_pct", "obp", "hr_pct"]
    for name, frames in (("J5_same_season", same), ("J5_next_season", nxt)):
        allf = pd.concat(frames)
        res[name] = {"batter_seasons": len(allf), **{k: {c: float(allf[k].corr(allf[c])) for c in cols} for k in METRICS}}
    res["all_seasons_pass"] = all(s["gates"]["pass"] for s in res["seasons"].values())
    (OUT / "jdv.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("J4_year_to_year", "J5_same_season", "J5_next_season", "all_seasons_pass")}, indent=1))


if __name__ == "__main__":
    main()
