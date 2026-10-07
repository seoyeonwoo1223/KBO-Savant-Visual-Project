"""EAA-CL1: 저평가 편향 분해와 추가 변인 단일 추가 진단. 등록: gates.md. 운영·상대 파일에는 쓰지 않는다."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "sinker_anchor_20261007"))
from common import FF, SEED, evaluation_groups, legacy_helpers, load, player_errors, sha  # noqa: E402

VARIABLES = ["primary_share", "share_FF", "share_SI", "share_FC", "ff_ivb_in", "ff_hb_arm_in",
             "primary_hb_arm_in", "primary_ivb_in", "primary_minus_FF_z55_over_height",
             "primary_minus_FF_side55_over_height", "primary_minus_FF_ivb_in", "primary_minus_FF_hb_arm_in",
             "game_height_ivb", "game_side_hb", "game_pair_support", "log_n"]
GROUPS = ["all", "FF", "SI", "SI_IVB_le10", "high60", "low20"]
Q95, QBON = [.025, .975], [.05/16/2, 1-.05/16/2]


def save(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def hashed(pitcher, k):
    return int(hashlib.sha256(pitcher.encode()).hexdigest(), 16) % k


def paired(d, reference, candidate):
    out, groups = {}, evaluation_groups(d)
    for name in GROUPS:
        if name not in groups: continue
        valid = groups[name] & np.isfinite(reference) & np.isfinite(candidate)
        b = player_errors(d.loc[valid], reference[valid]); c = player_errors(d.loc[valid], candidate[valid])
        rec = {"rows": int(valid.sum()), "players": len(b), "ref_MAE": float(b.MAE.mean()), "ref_bias": float(b.bias.mean()),
               "cand_MAE": float(c.MAE.mean()), "cand_bias": float(c.bias.mean()),
               "ref_downside": float(b.downside.mean()), "cand_downside": float(c.downside.mean())}
        if len(b) >= 2:
            idx = np.random.default_rng(SEED).integers(0, len(b), size=(2000, len(b)))
            for key in ["MAE", "downside"]:
                gain = b[key].to_numpy() - c[key].to_numpy(); boot = gain[idx].mean(axis=1)
                rec[key+"_gain"] = {"mean": float(gain.mean()), "ci95": np.quantile(boot, Q95).tolist(),
                                    "ci_bonferroni16": np.quantile(boot, QBON).tolist()}
        out[name] = rec
    return out


def calibration(d, prediction):
    t = pd.DataFrame({"p": d.pitcher.to_numpy(), "obs": d.arm_angle.to_numpy(), "pred": prediction}).groupby("p").mean()
    x, y = t.pred.to_numpy(), t.obs.to_numpy()
    def fit(i): return np.polyfit(x[i], y[i], 1)
    slope, intercept = fit(np.arange(len(t)))
    idx = np.random.default_rng(SEED).integers(0, len(t), size=(2000, len(t)))
    boots = np.array([fit(i) for i in idx])
    bins = {}
    for by in ["obs", "pred"]:
        q = pd.qcut(t[by], 5, labels=False)
        bins[by] = [{"quintile": int(k), "players": int((q == k).sum()), "range": [float(t[by][q == k].min()), float(t[by][q == k].max())],
                     "bias": float((t.pred - t.obs)[q == k].mean())} for k in range(5)]
    return {"players": len(t), "slope": float(slope), "intercept": float(intercept),
            "slope_ci95": np.quantile(boots[:, 0], Q95).tolist(), "intercept_ci95": np.quantile(boots[:, 1], Q95).tolist(),
            "bias_by_quintile": bins}


def main():
    ridge_fit, training_weights, *_ = legacy_helpers()
    h = load("MLB", labelled=True)
    h["log_n"] = np.log(h.n)
    ref = pd.read_parquet(HERE.parent / "sinker_anchor_20261007/inputs/MLB_OOF_predictions_reference.parquet")
    h = h.merge(ref[["pitcher", "season", "anchor"]], on=["pitcher", "season"], validate="one_to_one")
    assert h.groupby("pitcher").outer_fold.nunique().max() == 1
    anchor = np.full(len(h), np.nan); recal = anchor.copy()
    added = {v: anchor.copy() for v in VARIABLES}
    fold_models, recal_params = {}, []
    for f in range(5):
        tr = h.loc[h.outer_fold.ne(f)].copy(); mk = h.outer_fold.eq(f).to_numpy(); va = h.loc[mk]
        assert set(tr.pitcher).isdisjoint(va.pitcher)
        base = ridge_fit(tr, FF); anchor[mk] = base.predict(va[FF].to_numpy(float))
        inner = tr.pitcher.map(lambda p: hashed(p, 4)).to_numpy(); inner_oof = np.full(len(tr), np.nan)
        for g in range(4):
            assert set(tr.pitcher[inner != g]).isdisjoint(tr.pitcher[inner == g])
            inner_oof[inner == g] = ridge_fit(tr.loc[inner != g], FF).predict(tr.loc[inner == g, FF].to_numpy(float))
        w = training_weights(tr)
        b, a = np.polyfit(inner_oof, tr.arm_angle.to_numpy(), 1, w=np.sqrt(w))
        recal[mk] = a + b*anchor[mk]; recal_params.append({"fold": f, "a": float(a), "b": float(b)})
        fold_models[f] = {"anchor": base}
        for v in VARIABLES:
            model = ridge_fit(tr, FF+[v]); added[v][mk] = model.predict(va[FF+[v]].to_numpy(float))
            fold_models[f][v] = model
    reproduction = float(np.max(abs(anchor - h.anchor.to_numpy())))
    assert reproduction < 1e-9

    part_a = {"calibration_anchor_OOF": calibration(h, anchor), "recalibration_fold_params": recal_params,
              "recalibration_paired": paired(h, anchor, recal)}
    part_a["calibration_by_group"] = {g: calibration(h.loc[m], anchor[m]) for g, m in evaluation_groups(h).items()
                                      if g in ["FF", "SI"]}
    rows, part_b = [], {}
    for v in VARIABLES:
        s = paired(h, anchor, added[v]); part_b[v] = s
        a, si, hi = s["all"], s["SI"], s["high60"]
        signal = (a["MAE_gain"]["mean"] >= .05 and a["MAE_gain"]["ci95"][0] > 0 and a["downside_gain"]["mean"] >= 0
                  and si["MAE_gain"]["mean"] >= -.10 and hi["MAE_gain"]["mean"] >= -.10)
        row = {"variable": v, "signal": bool(signal), "bonferroni_lower_gt0": bool(a["MAE_gain"]["ci_bonferroni16"][0] > 0)}
        for g in GROUPS:
            if g in s:
                row[g+"_players"] = s[g]["players"]; row[g+"_MAE_gain"] = s[g]["MAE_gain"]["mean"]
                row[g+"_downside_gain"] = s[g]["downside_gain"]["mean"]; row[g+"_bias"] = s[g]["cand_bias"]
        row["all_MAE_gain_lo95"], row["all_MAE_gain_hi95"] = a["MAE_gain"]["ci95"]
        rows.append(row)
    table = pd.DataFrame(rows); table.to_csv(HERE / "CL1_variable_screen.csv", index=False)

    # 재사용 월 보조: 같은 투수 fold 모델, FF100·label95만
    foldmap = h.groupby("pitcher").outer_fold.first().to_dict(); monthly = []
    for month in ["May", "July"]:
        d = load(month, labelled=True); d["log_n"] = np.log(d.n)
        d = d.loc[d.label95.fillna(False) & d.n_ff.ge(100) & np.isfinite(d[FF]).all(axis=1) & d.arm_angle.notna()].reset_index(drop=True)
        d["fold"] = [int(foldmap[p]) if p in foldmap else hashed(p, 5) for p in d.pitcher]
        preds = {k: np.full(len(d), np.nan) for k in ["anchor"]+VARIABLES}
        for f in range(5):
            mk = d.fold.eq(f).to_numpy()
            assert set(d.pitcher[mk]).isdisjoint(h.pitcher[h.outer_fold.ne(f)])
            if not mk.any(): continue
            for k, model in fold_models[f].items():
                cols = FF if k == "anchor" else FF+[k]
                preds[k][mk] = model.predict(d.loc[mk, cols].to_numpy(float))
        d["month"] = month; monthly.append((d, preds))
    md = pd.concat([m[0] for m in monthly], ignore_index=True)
    mp = {k: np.concatenate([m[1][k] for m in monthly]) for k in monthly[0][1]}
    month_b = {v: paired(md, mp["anchor"], mp[v]) for v in VARIABLES}
    month_a = {"calibration_anchor": calibration(md, mp["anchor"])}

    kbo = load("KBO_all"); kbo["log_n"] = np.log(kbo.n)
    kbo_cov = {v: ({"available": True, "rows": int(kbo[v].notna().sum()),
                    "KBO_q10_50_90": np.nanquantile(kbo[v], [.1, .5, .9]).tolist(),
                    "MLB_q10_50_90": np.nanquantile(h[v], [.1, .5, .9]).tolist()} if v in kbo else {"available": False})
               for v in VARIABLES}
    save("CL1_results.json", {"registration": "gates.md", "gates_sha256": sha(HERE / "gates.md"), "code_sha256": sha(__file__),
        "population": {"rows": len(h), "players": int(h.pitcher.nunique()), "monthly_rows": len(md), "monthly_players": int(md.pitcher.nunique())},
        "anchor_reproduction_max_abs": reproduction, "part_A": part_a, "part_B": part_b,
        "monthly_reused": {"part_A": month_a, "part_B": month_b, "period_reused": True},
        "KBO_input_coverage": kbo_cov, "KBO_reference_angles_used": False,
        "candidate_selected": False, "operational_changed": False})
    print("CL1_DONE", len(h), h.pitcher.nunique(), len(md), reproduction, flush=True)


if __name__ == "__main__":
    main()
