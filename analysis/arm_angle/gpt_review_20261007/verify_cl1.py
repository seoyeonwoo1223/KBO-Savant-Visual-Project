"""0003의 계산을 NumPy 정상방정식과 별도 통계로 검산한다. 상대 파일은 읽기만 한다."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
INPUTS = HERE.parent / "sinker_anchor_20261007/inputs"
PEER = HERE.parent / "claude_review_20261007"
PEER_SHA = "53ec40c37c85139e346e27d50226e5c8e9ae4356"
ORIGINAL_SHA = "661a5c0229f6b6f274458221d6230b22bfa700b9"
SEED = 20261007
FF = ["height_m", "left_hand", "z55_over_height", "side55_over_height", "ff_speed55",
      "ff_armside_vx_over_minus_vy", "ff_vz_over_minus_vy", "ff_flight55_to_plate",
      "ff_movement_axis_arm_sin", "ff_movement_axis_up_cos", "ff_movement_size_m"]
VARIABLES = ["primary_share", "share_FF", "share_SI", "share_FC", "ff_ivb_in", "ff_hb_arm_in",
             "primary_hb_arm_in", "primary_ivb_in", "primary_minus_FF_z55_over_height",
             "primary_minus_FF_side55_over_height", "primary_minus_FF_ivb_in", "primary_minus_FF_hb_arm_in",
             "game_height_ivb", "game_side_hb", "game_pair_support", "log_n"]
CHECKED = 0
MAX_DIFFERENCE = 0.0


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(population, labelled=True):
    d = pd.read_parquet(INPUTS / f"{population}_inputs.parquet")
    assert "arm_angle" not in d and d.row_id.is_unique
    if labelled:
        t = pd.read_parquet(INPUTS / f"{population}_targets.parquet")
        d = d.merge(t, on="row_id", validate="one_to_one", how="left")
    d["log_n"] = np.log(d.n)
    return d


def weights(d):
    w = 1 / d.pitcher.map(d.pitcher.value_counts()).to_numpy(float)
    w *= np.where(d.arm_angle.ge(60), 4.0, 1.0)
    return w / w.mean()


def polynomial(x):
    return np.column_stack([x] + [x[:, i] * x[:, j] for i in range(x.shape[1]) for j in range(i, x.shape[1])])


def fit(d, columns):
    assert "arm_angle" not in columns and not set(columns) & {"pitcher", "season", "outer_fold", "fixed_training_row"}
    raw = d[columns].to_numpy(float)
    med = np.array([np.median(c[np.isfinite(c)]) if np.isfinite(c).any() else 0.0 for c in raw.T])
    x = polynomial(np.where(np.isfinite(raw), raw, med))
    w = weights(d)
    center = np.average(x, axis=0, weights=w)
    variance = np.average((x-center)**2, axis=0, weights=w)
    # StandardScaler가 상수로 판정하는 부동소수점 상한과 같은 정의.
    eps = np.finfo(float).eps
    constant = variance <= len(d)*eps*variance + (len(d)*center*eps)**2
    scale = np.where(constant, 1.0, np.sqrt(variance))
    z = (x-center)/scale
    intercept = np.average(d.arm_angle, weights=w)
    coef = np.linalg.solve(z.T @ (w[:, None]*z) + 100*np.eye(z.shape[1]), z.T @ (w*(d.arm_angle-intercept)))
    return columns, med, center, scale, np.asarray(coef), float(intercept)


def predict(model, d):
    columns, med, center, scale, coef, intercept = model
    raw = d[columns].to_numpy(float)
    return (polynomial(np.where(np.isfinite(raw), raw, med))-center)/scale @ coef + intercept


def linear(x, y, w=None):
    w = np.ones(len(x)) if w is None else w
    mx, my = np.average(x, weights=w), np.average(y, weights=w)
    slope = np.sum(w*(x-mx)*(y-my))/np.sum(w*(x-mx)**2)
    return float(slope), float(my-slope*mx)


def assert_close(actual, expected, label):
    global CHECKED, MAX_DIFFERENCE
    a, b = np.asarray(actual, float), np.asarray(expected, float)
    np.testing.assert_allclose(a, b, atol=1e-8, rtol=0, err_msg=label)
    CHECKED += a.size
    MAX_DIFFERENCE = max(MAX_DIFFERENCE, float(np.max(np.abs(a-b))))


def masks(d):
    return {"all": np.ones(len(d), bool), "FF": d.primary4.eq("FF").to_numpy(),
            "SI": d.primary4.eq("SI").to_numpy(),
            "SI_IVB_le10": (d.primary4.eq("SI") & d.type_SI_ivb_in.le(10)).to_numpy(),
            "high60": d.arm_angle.ge(60).to_numpy(), "low20": d.arm_angle.lt(20).to_numpy()}


def paired(d, reference, candidate, expected):
    for group, mask in masks(d).items():
        if group not in expected: continue
        error_b, error_c = reference[mask]-d.arm_angle.to_numpy()[mask], candidate[mask]-d.arm_angle.to_numpy()[mask]
        t = pd.DataFrame({"pitcher": d.pitcher.to_numpy()[mask], "ref_MAE": abs(error_b), "cand_MAE": abs(error_c),
                          "ref_bias": error_b, "cand_bias": error_c,
                          "ref_downside": np.maximum(-error_b, 0), "cand_downside": np.maximum(-error_c, 0)}).groupby("pitcher").mean()
        rec = expected[group]
        assert len(t) == rec["players"] and int(mask.sum()) == rec["rows"]
        for c in t: assert_close(t[c].mean(), rec[c], group+":"+c)
        if len(t) < 2: continue
        idx = np.random.default_rng(SEED).integers(0, len(t), size=(2000, len(t)))
        for key in ["MAE", "downside"]:
            gain = (t["ref_"+key]-t["cand_"+key]).to_numpy()
            assert_close(gain.mean(), rec[key+"_gain"]["mean"], group+":gain")
            boot = gain[idx].mean(axis=1)
            for name, q in [("ci95", [.025, .975]), ("ci_bonferroni16", [.05/32, 1-.05/32])]:
                assert_close(np.quantile(boot, q), rec[key+"_gain"][name], group+":"+name)


def calibration(d, prediction, expected):
    t = pd.DataFrame({"pitcher": d.pitcher.to_numpy(), "obs": d.arm_angle.to_numpy(), "pred": prediction}).groupby("pitcher").mean()
    x, y = t.pred.to_numpy(), t.obs.to_numpy()
    b, a = linear(x, y)
    idx = np.random.default_rng(SEED).integers(0, len(t), size=(2000, len(t)))
    boots = np.array([linear(x[i], y[i]) for i in idx])
    assert_close([b, a], [expected["slope"], expected["intercept"]], "OLS")
    assert_close(np.quantile(boots[:, 0], [.025, .975]), expected["slope_ci95"], "OLS slope interval")
    assert_close(np.quantile(boots[:, 1], [.025, .975]), expected["intercept_ci95"], "OLS intercept interval")
    for col in ["obs", "pred"]:
        q = pd.qcut(t[col], 5, labels=False)
        for k, rec in enumerate(expected["bias_by_quintile"][col]):
            assert int((q==k).sum()) == rec["players"]
            assert_close((t.pred-t.obs)[q==k].mean(), rec["bias"], col+":bias")


def models_and_predictions(h):
    predictions = {v: np.full(len(h), np.nan) for v in ["anchor", "recalibration"]+VARIABLES}
    models, audit, params = {}, [], []
    for f in range(5):
        tr, mk = h.loc[h.outer_fold.ne(f)].copy(), h.outer_fold.eq(f).to_numpy()
        va = h.loc[mk]
        assert set(tr.pitcher).isdisjoint(va.pitcher)
        models[f] = {"anchor": fit(tr, FF)}
        predictions["anchor"][mk] = predict(models[f]["anchor"], va)
        inner = tr.pitcher.map(lambda p: int(hashlib.sha256(p.encode()).hexdigest(), 16) % 4).to_numpy()
        oof = np.full(len(tr), np.nan)
        for g in range(4):
            it, iv = tr.loc[inner!=g], tr.loc[inner==g]
            assert set(it.pitcher).isdisjoint(iv.pitcher)
            oof[inner==g] = predict(fit(it, FF), iv)
            audit.append({"outer": f, "inner": g, "training_players": it.pitcher.nunique(),
                          "validation_players": iv.pitcher.nunique(), "player_overlap": 0})
        b, a = linear(oof, tr.arm_angle.to_numpy(), weights(tr))
        predictions["recalibration"][mk] = a+b*predictions["anchor"][mk]
        params.append({"fold": f, "a": a, "b": b})
        for v in VARIABLES:
            models[f][v] = fit(tr, FF+[v])
            predictions[v][mk] = predict(models[f][v], va)
    return models, predictions, audit, params


def monthly_predictions(h, models):
    lookup = h.groupby("pitcher").outer_fold.first().to_dict()
    frames, predictions = [], {v: [] for v in ["anchor"]+VARIABLES}
    for month in ["May", "July"]:
        d = read(month)
        eligible = d.label95.fillna(False) & d.n_ff.ge(100) & np.isfinite(d[FF]).all(axis=1) & d.arm_angle.notna()
        d = d.loc[eligible].reset_index(drop=True)
        d["evaluation_fold"] = [lookup[p] if p in lookup else int(hashlib.sha256(p.encode()).hexdigest(), 16)%5 for p in d.pitcher]
        d["month"] = month
        p = {v: np.full(len(d), np.nan) for v in predictions}
        for f, bundle in models.items():
            mk = d.evaluation_fold.eq(f).to_numpy()
            assert set(d.loc[mk, "pitcher"]).isdisjoint(h.loc[h.outer_fold.ne(f), "pitcher"])
            if mk.any():
                for v in p: p[v][mk] = predict(bundle[v], d.loc[mk])
        frames.append(d)
        for v in p: predictions[v].append(p[v])
    return pd.concat(frames, ignore_index=True), {v: np.concatenate(a) for v, a in predictions.items()}


def input_shift_and_sensitivity(h):
    k = read("KBO_all", False)
    k = k.loc[k.n_ff.ge(100) & np.isfinite(k[FF]).all(axis=1)]
    expected = pd.read_csv(PEER/"KBO_FF_input_shift.csv").set_index("feature")
    for col in FF+["ff_ivb_in", "ff_hb_arm_in"]:
        m, x = h[col].to_numpy(float), k[col].to_numpy(float)
        lo, hi = np.quantile(m, [.01, .99])
        assert_close([(x<lo).mean(), (x>hi).mean()], expected.loc[col, ["KBO_below_MLB_q01", "KBO_above_MLB_q99"]], "KBO range")
    model = fit(h, FF)
    base = predict(model, k)
    clips = json.loads((PEER/"KBO_clip_sensitivity.json").read_text())["sensitivity"]
    for key, rec in clips.items():
        cols = FF if key == "all_FF11" else key.split("+")
        d = k.copy()
        for c in cols: d[c] = d[c].clip(*np.quantile(h[c], [.01, .99]))
        delta = predict(model, d)-base
        changed = abs(delta)>1e-9
        assert int(changed.sum()) == rec["rows_changed"]
        assert_close([delta.mean(), delta[changed].mean()], [rec["mean_delta_all"], rec["mean_delta_changed"]], "clip delta")
        assert_close(np.quantile(delta[changed], [.1, .5, .9]), rec["q10_50_90_changed"], "clip quantiles")
    return len(k)


def provenance_check(h):
    q = pd.concat([pd.read_parquet(HERE.parent/"sinker_anchor_20261007"/(m+"_sinker_predictions.parquet")) for m in ["May", "July"]])
    fixed = set(h.loc[h.fixed_training_row, "pitcher"])
    seen = q.pitcher.isin(fixed)
    v1 = json.loads((ROOT/"data/models/estimated_arm_angle_v1.json").read_text())
    flag_source = "shared historical fixed cohort used by R2; no v1 training membership assertion in committed inputs"
    path_metrics = {}
    for key in ["reference", "SI_physics"]:
        error = q[key]-q.arm_angle
        per_player = pd.DataFrame({"pitcher":q.pitcher.to_numpy(), "MAE":abs(error).to_numpy(),
                                   "bias":error.to_numpy(), "downside":np.maximum(-error.to_numpy(),0)}).groupby("pitcher").mean()
        path_metrics[key] = per_player.mean().to_dict()
    return {"SI_month_rows": len(q), "SI_month_players": q.pitcher.nunique(),
            "overlap_fixed_cohort_rows": int(seen.sum()), "overlap_fixed_cohort_players": q.loc[seen, "pitcher"].nunique(),
            "fixed_cohort_rows": int(h.fixed_training_row.sum()), "fixed_cohort_players": len(fixed),
            "flag_meaning": flag_source, "v1_training_overlap_23_rows_verified": False,
            "v1_model_has_training_player_registry": False, "v1_angle_features": v1["angle"]["features"],
            "v1_full_player_separation_verified": False, "SI_month_path_metrics":path_metrics,
            "both_monthly_paths_have_positive_population_bias":all(v["bias"]>0 for v in path_metrics.values())}


def registration_and_integrity():
    old_path = "analysis/arm_angle/sinker_anchor_20261007/gates.md"
    original = subprocess.check_output(["git", "show", ORIGINAL_SHA+":"+old_path], cwd=ROOT)
    now = (ROOT/old_path).read_bytes()
    assert now.startswith(original)
    lock = json.loads((HERE.parent/"sinker_anchor_20261007/experiment-lock.json").read_text())
    changed = [name for name, sha in lock["files"].items() if digest(HERE.parent/"sinker_anchor_20261007"/name) != sha]
    assert changed == ["gates.md"]
    gates_path = "analysis/arm_angle/claude_review_20261007/gates.md"
    registered = subprocess.check_output(["git", "show", "7afecdf91ecfe893e04dfda70ce3f4e6f566ccdc:"+gates_path], cwd=ROOT)
    assert registered == (PEER/"gates.md").read_bytes()
    return {"CL1_gates_unchanged": True, "original_registered_gates_byte_prefix_preserved": True,
            "original_package_lock_changed": changed, "original_SHA_verification_requires_pinned_661a5c02": True}


def main():
    expected = json.loads((PEER/"CL1_results.json").read_text())
    h = read("MLB")
    models, p, audit, params = models_and_predictions(h)
    ref = pd.read_parquet(INPUTS/"MLB_OOF_predictions_reference.parquet")
    reference = h.merge(ref[["pitcher", "season", "anchor"]], on=["pitcher", "season"], validate="one_to_one")
    assert_close(p["anchor"], reference.anchor, "anchor OOF")
    a = expected["part_A"]
    calibration(h, p["anchor"], a["calibration_anchor_OOF"])
    for group in ["FF", "SI"]:
        mk = masks(h)[group]
        calibration(h.loc[mk], p["anchor"][mk], a["calibration_by_group"][group])
    for actual, saved in zip(params, a["recalibration_fold_params"]): assert_close([actual["a"], actual["b"]], [saved["a"], saved["b"]], "recalibration")
    paired(h, p["anchor"], p["recalibration"], a["recalibration_paired"])
    for v in VARIABLES: paired(h, p["anchor"], p[v], expected["part_B"][v])
    d, mp = monthly_predictions(h, models)
    calibration(d, mp["anchor"], expected["monthly_reused"]["part_A"]["calibration_anchor"])
    for v in VARIABLES: paired(d, mp["anchor"], mp[v], expected["monthly_reused"]["part_B"][v])
    screen = pd.read_csv(PEER/"CL1_variable_screen.csv")
    assert len(screen) == 16 and not screen.signal.any()
    for v in VARIABLES:
        s = expected["part_B"][v]
        all_ = s["all"]
        signal = (all_["MAE_gain"]["mean"] >= .05 and all_["MAE_gain"]["ci95"][0] > 0
                  and all_["downside_gain"]["mean"] >= 0 and s["SI"]["MAE_gain"]["mean"] >= -.1
                  and s["high60"]["MAE_gain"]["mean"] >= -.1)
        assert not signal
    kbo_rows = input_shift_and_sensitivity(h)
    stats = a["calibration_anchor_OOF"]
    rule_mean_reversion = (stats["slope_ci95"][0] <= 1 <= stats["slope_ci95"][1]
                          and all(abs(r["bias"]) <= .5 for r in stats["bias_by_quintile"]["pred"]))
    rule_compression = stats["slope_ci95"][0] > 1
    assert not rule_mean_reversion and not rule_compression
    h[["row_id", "pitcher", "season", "arm_angle", "outer_fold"]].assign(**p).to_parquet(HERE/"MLB_independent_predictions.parquet", index=False)
    d[["row_id", "pitcher", "month", "arm_angle", "evaluation_fold"]].assign(**mp).to_parquet(HERE/"monthly_independent_predictions.parquet", index=False)
    result = {"passed": True, "peer_commit": PEER_SHA, "rows": len(h), "players": h.pitcher.nunique(),
              "monthly_rows": len(d), "monthly_players": d.pitcher.nunique(), "KBO_FF100_rows": kbo_rows,
              "independent_normal_equation_models": 106, "checked_numeric_values": CHECKED,
              "maximum_absolute_difference": MAX_DIFFERENCE, "inner_splits": audit, "recalibration_params": params,
              "registered_mean_reversion_rule_satisfied": False, "registered_compression_rule_satisfied": False,
              "Bonferroni16_quantiles": [.05/32, 1-.05/32], "bootstrap_draws_expected_in_each_Bonferroni_tail": 2000*.05/32,
              "baseline_provenance": provenance_check(h), "registration_integrity": registration_and_integrity(),
              "KBO_reference_angles_used": False, "new_confirmation": False, "operational_changed": False}
    (HERE/"verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    print("INDEPENDENT_VERIFIED", CHECKED, "values", result["maximum_absolute_difference"], "maxdiff", flush=True)


if __name__ == "__main__": main()
