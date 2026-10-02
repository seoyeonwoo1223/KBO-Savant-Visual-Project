"""C1 구심 시즌 p_zone 카운트 추가 + C1-ABS 대조 (gates.md C1).

python analysis/sbj_formula/c1_count_pzone.py --base c0a 2019 2020 ...
결과: results/c1_<season>.json, 구심 시즌 선수 변화표 results/c1_player_changes_<season>.csv
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import sbj_exp as E  # noqa: E402
from visualbaseball import zone_decision as zd  # noqa: E402

BASES = {"b0": {"seeds": (E.RS,), "es": "auto"}, "c0a": {"seeds": (E.RS,), "es": False},
         "c0b": {"seeds": tuple(range(E.RS, E.RS + 5)), "es": "auto"}}
COUNT = ("balls_before", "strikes_before")
OUT = Path(__file__).with_name("results")


def strata(df):
    return {"0strike": df.strikes == 0, "1strike": df.strikes == 1, "2strike": df.strikes == 2, "3ball": df.balls == 3}


def calibration(take, p):
    out = {}
    for name, mask in strata(take).items():
        m = mask.to_numpy()
        out[name] = {"n": int(m.sum()), "observed_minus_pred": float(take.take_cs.to_numpy()[m].mean() - p[m].mean()) if m.any() else None}
    return out


def ranks(s):
    return s.rank(ascending=False, method="min")


def season(y, base):
    cfg = BASES[base]
    rows = E.rows_for(y)
    fields = zd.pzone_fields(y)
    cache = E.CACHE / f"{base}_{y}.npz"
    if cache.exists():
        ordered, fold, _ = E.ordered_folds(rows)
        z = np.load(cache)
        ref = {"rows": ordered, "fold": fold, "p_swing": z["p_swing"], "p_zone": z["p_zone"]}
    else:
        ref = E.crossfit(rows, fields, seeds=cfg["seeds"], es=cfg["es"])
        np.savez(cache, p_swing=ref["p_swing"], p_zone=ref["p_zone"])
    cand = E.crossfit(rows, tuple(fields) + COUNT, pswing=False, seeds=cfg["seeds"], es=cfg["es"])
    assert all(a is b for a, b in zip(cand["rows"], ref["rows"]))
    fb = E.frame(ref); fc = E.frame(cand, p_swing=ref["p_swing"])

    take = fb.swing.to_numpy() == 0
    tb, tc = fb[take], fc[take]
    lb, lc = E.bernoulli_loss(tb.take_cs, tb.p_zone).to_numpy(), E.bernoulli_loss(tc.take_cs, tc.p_zone).to_numpy()
    d_all, z_all = E.cluster_z(lb, lc, tb.game_id)
    bnd = tb.p_zone.between(.1, .9).to_numpy()
    d_bnd, z_bnd = E.cluster_z(lb[bnd], lc[bnd], tb.game_id.to_numpy()[bnd])
    own_bnd = tc.p_zone.between(.1, .9).to_numpy()

    sb, sc = E.player_sbj(fb), E.player_sbj(fc)
    rb, rc = ranks(sb), ranks(sc)
    shift = (rb - rc).abs()
    names = {str(r["batter_id"]): r.get("batter_name") for r in rows}
    changes = pd.DataFrame({"batter_id": sb.index, "batter_name": [names.get(i) for i in sb.index],
                            "sbj_base": sb.values, "sbj_c1": sc[sb.index].values, "delta": (sc[sb.index] - sb).values,
                            "rank_base": rb.values, "rank_c1": rc[sb.index].values}).sort_values("rank_base")
    rep_b, rep_c = E.block_reproducibility(fb), E.block_reproducibility(fc)
    out = {
        "season": y, "base": base, "pzone_fields_base": list(fields), "pzone_fields_c1": list(fields) + list(COUNT),
        "takes": int(take.sum()), "boundary_takes": int(bnd.sum()),
        "take_log_loss": {"base": float(lb.mean()), "c1": float(lc.mean()), "delta": d_all, "cluster_z": z_all},
        "boundary_log_loss": {"base": float(lb[bnd].mean()), "c1": float(lc[bnd].mean()), "delta": d_bnd, "cluster_z": z_bnd},
        "boundary_calibration": {"base": calibration(tb[bnd], tb.p_zone.to_numpy()[bnd]), "c1": calibration(tc[bnd], tc.p_zone.to_numpy()[bnd])},
        "own_boundary_calibration_c1": calibration(tc[own_bnd], tc.p_zone.to_numpy()[own_bnd]),
        "players": {"qualified": len(sb), "qualification_changes": int(len(sb.index.symmetric_difference(sc.index))),
                    "mean_abs_delta": float((sc[sb.index] - sb).abs().mean()), "max_abs_delta": float((sc[sb.index] - sb).abs().max()),
                    "spearman": float(sb.rank().corr(sc[sb.index].rank())), "max_rank_shift": int(shift.max()),
                    "moved_5_or_more": int((shift >= 5).sum())},
        "block_reproducibility": {"base": rep_b, "c1": rep_c, "base_mean": float(np.mean(rep_b)), "c1_mean": float(np.mean(rep_c))},
        "seconds_c1_pzone": cand["seconds"],
    }
    if y < zd.ABS_FIRST_SEASON:
        cal = out["boundary_calibration"]["c1"]
        judged = {k: v for k, v in cal.items() if v["n"] >= 300}
        out["gates"] = {
            "C1-1": {"strata": judged, "pass": all(abs(v["observed_minus_pred"]) <= .02 for v in judged.values())},
            "C1-2": {"delta": d_all, "z": z_all, "pass": d_all < 0 and z_all < -2},
            "C1-3": {"base": out["block_reproducibility"]["base_mean"], "c1": out["block_reproducibility"]["c1_mean"],
                     "pass": out["block_reproducibility"]["c1_mean"] >= out["block_reproducibility"]["base_mean"] - .05},
        }
        out["gates"]["pass"] = all(g["pass"] for g in out["gates"].values())
        changes.to_csv(OUT / f"c1_player_changes_{y}.csv", index=False, float_format="%.4f")
    else:
        out["gates"] = {"A1": {"z_all": z_all, "z_boundary": z_bnd, "no_significant_gain": z_all > -2}}
    (OUT / f"c1_{y}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(y, json.dumps(out["gates"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--base", required=True, choices=BASES); ap.add_argument("seasons", nargs="+", type=int)
    args = ap.parse_args()
    for y in args.seasons:
        season(y, args.base)
