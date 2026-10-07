"""저장 예측·학습 분할·입력 잠금·회귀를 별도 계산으로 검산한다."""
from __future__ import annotations

import json
import pickle
import subprocess

import numpy as np
import pandas as pd
from sklearn.preprocessing import PolynomialFeatures

from common import OUT, FF, SI_GEOMETRY, SI_PHYSICS, load, sha, save, eligible_si


def independent_ridge(training, validation, columns):
    x = PolynomialFeatures(2,include_bias=False).fit_transform(training[columns].to_numpy(float))
    xv = PolynomialFeatures(2,include_bias=False).fit_transform(validation[columns].to_numpy(float))
    w = 1/training.pitcher.map(training.pitcher.value_counts()).to_numpy(float)
    w *= np.where(training.arm_angle.ge(60),4.,1.)
    w /= w.mean()
    center = np.average(x,axis=0,weights=w)
    scale = np.sqrt(np.average((x-center)**2,axis=0,weights=w))
    scale = np.where(scale>1e-12,scale,1)
    z = (x-center)/scale
    y = training.arm_angle.to_numpy(float)
    intercept = np.average(y,weights=w)
    coef = np.linalg.solve(z.T@(w[:,None]*z)+100*np.eye(z.shape[1]), z.T@(w*(y-intercept)))
    return (xv-center)/scale@coef+intercept


def independent_values(frame, prediction, mask):
    valid = np.asarray(mask,bool) & np.isfinite(prediction) & frame.arm_angle.notna().to_numpy()
    q = frame.loc[valid]
    e = np.asarray(prediction)[valid]-q.arm_angle.to_numpy()
    errors = pd.DataFrame({"pitcher":q.pitcher.to_numpy(),"MAE":np.abs(e),"bias":e,
        "downside":np.clip(-e,0,None),"upside":np.clip(e,0,None)}).groupby("pitcher").mean()
    values = {"rows":int(valid.sum()),"players":len(errors)}
    if len(errors):
        values.update({c:float(errors[c].mean()) for c in errors})
        count = max(1,int(np.ceil(len(errors)*.2)))
        values["downside_tail20"] = float(np.sort(errors.downside.to_numpy())[-count:].mean())
    return values, errors


def verify_scores(prefix, frame, prediction, group_masks, reference_key):
    scores = json.loads((OUT/(prefix+"_scores.json")).read_text())
    checked, maximum, paired_checks = 0, 0., 0
    for model, groups in scores["metrics"].items():
        for group, expected in groups.items():
            actual, _ = independent_values(frame,prediction[model],group_masks[group])
            for key,value in actual.items():
                difference = abs(value-expected[key])
                maximum = max(maximum,difference)
                assert difference<1e-9,(prefix,model,group,key)
                checked += 1
    paired_key = "paired_vs_reference" if reference_key=="reference" else "paired_vs_full"
    for model, groups in scores[paired_key].items():
        for group, expected in groups.items():
            mask = np.asarray(group_masks[group]) & np.isfinite(prediction[model]) & np.isfinite(prediction[reference_key])
            _, b = independent_values(frame,prediction[reference_key],mask)
            _, c = independent_values(frame,prediction[model],mask)
            assert b.index.equals(c.index)
            if not len(b):continue
            rng = np.random.default_rng(20261007)
            indices = rng.integers(0,len(b),size=(2000,len(b)))
            for key in ["MAE","downside","upside"]:
                gain = b[key].to_numpy()-c[key].to_numpy()
                e = expected[key+"_gain"]
                assert abs(gain.mean()-e["mean"])<1e-9
                if len(b)>1:np.testing.assert_allclose(np.quantile(gain[indices].mean(axis=1),[.025,.975]),e["bootstrap95"],atol=1e-9,rtol=0)
                paired_checks += 3 if len(b)>1 else 1
            gain = abs(b.bias.mean())-abs(c.bias.mean())
            e = expected["abs_population_bias_gain"]
            assert abs(gain-e["mean"])<1e-9
            if len(b)>1:
                draws = abs(b.bias.to_numpy()[indices].mean(axis=1))-abs(c.bias.to_numpy()[indices].mean(axis=1))
                np.testing.assert_allclose(np.quantile(draws,[.025,.975]),e["bootstrap95"],atol=1e-9,rtol=0)
            paired_checks += 3 if len(b)>1 else 1
    return checked,maximum,paired_checks


def main():
    lock = json.loads((OUT/"experiment-lock.json").read_text())
    for filename,digest in lock["files"].items():assert sha(OUT/filename)==digest,filename
    repository = OUT.parents[2]
    original = subprocess.check_output(["git","show",lock["registered_commit"]+":analysis/arm_angle/sinker_anchor_20261007/gates.md"],cwd=repository)
    assert original==(OUT/"gates.md").read_bytes()
    source = json.loads((OUT/"inputs/source_manifest.json").read_text())
    prior = {}
    for folder,meta in source["prior_manifests"].items():
        path = repository/"analysis/arm_angle"/folder/"RESULTS-MANIFEST.json"
        if not path.exists():continue
        assert sha(path)==meta["sha256"]
        manifest = json.loads(path.read_text())
        for filename,entry in manifest["files"].items():assert sha(path.parent/filename)==entry["sha256"]
        prior[folder]=len(manifest["files"])
    for version in ["v1","v3"]:
        assert sha(repository/f"data/models/estimated_arm_angle_{version}.json")==source[f"operational_{version}_sha256"]
    for population in ["MLB","May","July","KBO_all","KBO_FF100"]:
        inputs = load(population)
        assert "arm_angle" not in inputs and inputs.row_id.is_unique
        assert np.isfinite(inputs.loc[eligible_si(inputs),SI_PHYSICS]).all().all()

    from common import evaluation_groups, legacy_helpers
    legacy_helpers()
    from run_support import groups as support_groups
    history = load("MLB",True)
    si = history.loc[eligible_si(history,True)].reset_index(drop=True)
    with (OUT/"sinker_models.pkl").open("rb") as f:bundles=pickle.load(f)
    with (OUT/"support_models.pkl").open("rb") as f:support=pickle.load(f)
    audit = json.loads((OUT/"sinker_audit.json").read_text())
    maximum_ridge, model_count = 0., 0
    pred = pd.read_parquet(OUT/"MLB_sinker_predictions.parquet")
    for fold,models in bundles["fold_models"].items():
        tr,va = si.loc[si.outer_fold.ne(fold)],si.loc[si.outer_fold.eq(fold)]
        assert set(tr.pitcher).isdisjoint(va.pitcher)
        for name,bundle in models.items():
            assert set(bundle["training"].pitcher)==set(tr.pitcher)
            actual = independent_ridge(tr,va,bundle["columns"])
            stored = pred.loc[pred.outer_fold.eq(fold),name].to_numpy()
            maximum_ridge=max(maximum_ridge,float(abs(actual-stored).max()))
            assert np.max(abs(actual-stored))<1e-8
            model_count+=1
    for name,columns in bundles["columns"].items():
        actual=independent_ridge(si,si,columns)
        stored=bundles["fixed_models"][name].predict(si[columns].to_numpy(float))
        assert np.max(abs(actual-stored))<1e-8
        maximum_ridge=max(maximum_ridge,float(abs(actual-stored).max()))
        model_count+=1
    scalar_checks, maximum_metrics, paired_checks = 0, 0., 0
    n,diff,npaired=verify_scores("MLB_OOF_reused_sinker",pred,{name:pred[name].to_numpy() for name in ["reference","SI_geometry","SI_physics"]},evaluation_groups(pred),"reference")
    scalar_checks+=n;maximum_metrics=max(maximum_metrics,diff);paired_checks+=npaired
    months=[]
    for month in ["May","July"]:
        p=pd.read_parquet(OUT/(month+"_sinker_predictions.parquet"))
        assert p.groupby("pitcher").evaluation_fold.nunique().max()==1
        for row in p.itertuples():
            for bundle in bundles["fold_models"][row.evaluation_fold].values():assert row.pitcher not in set(bundle["training"].pitcher)
        q=load(month,True);q=q.loc[eligible_si(q,True)]
        assert set(q.row_id)==set(p.row_id)
        n,diff,npaired=verify_scores(month+"2025_reused_sinker",p,{name:p[name].to_numpy() for name in ["reference","SI_geometry","SI_physics"]},evaluation_groups(p),"reference")
        scalar_checks+=n;maximum_metrics=max(maximum_metrics,diff);paired_checks+=npaired
        months.append(p)
    monthly=pd.concat(months,ignore_index=True)
    assert monthly.groupby("pitcher").evaluation_fold.nunique().max()==1
    n,diff,npaired=verify_scores("MayJuly2025_reused_sinker",monthly,{name:monthly[name].to_numpy() for name in ["reference","SI_geometry","SI_physics"]},evaluation_groups(monthly),"reference")
    scalar_checks+=n;maximum_metrics=max(maximum_metrics,diff);paired_checks+=npaired

    sp=pd.read_parquet(OUT/"MLB_support_predictions.parquet")
    columns=["anchor","full","drop_support","constant_support","support_q10","support_q50","support_q90"]
    n,diff,npaired=verify_scores("MLB_OOF_reused_support",history,{name:sp[name].to_numpy() for name in columns},support_groups(history),"full")
    scalar_checks+=n;maximum_metrics=max(maximum_metrics,diff);paired_checks+=npaired
    constant_max=float(abs(sp.constant_support-sp.drop_support).max())
    assert constant_max<1e-8
    for fold,models in support["outer"].items():
        training=history.loc[history.outer_fold.ne(fold)]
        validation=history.loc[history.outer_fold.eq(fold)]
        assert set(training.pitcher).isdisjoint(validation.pitcher)
        for model in models.values():
            assert set(model["training_players"])==set(training.pitcher)
            for split in model["inner_splits"]:
                assert set(split["training_players"]).isdisjoint(split["validation_players"])
                assert set(split["training_players"]+split["validation_players"])==set(training.pitcher)
            support_index=model["indices"].index(12) if 12 in model["indices"] else None
            if model["variant"]=="constant_support":assert not model["projection"]["keep"][support_index]
            np.testing.assert_allclose(model["constant"],np.median(training.game_pair_support),atol=0,rtol=0)
            for key,quantile in [("support_q10",.1),("support_q50",.5),("support_q90",.9)]:
                assert model["quantiles"][key]==np.quantile(training.game_pair_support,quantile)
    for month in ["May","July"]:
        q=load(month,True);q=q.loc[q.FF100_evaluation_eligible].reset_index(drop=True)
        p=pd.read_csv(OUT/(month+"_support_predictions.csv"),dtype={"pitcher":str},float_precision="round_trip")
        n,diff,npaired=verify_scores(month+"2025_reused_support",q,{name:p[name].to_numpy() for name in columns},support_groups(q),"full")
        scalar_checks+=n;maximum_metrics=max(maximum_metrics,diff);paired_checks+=npaired
        constant_max=max(constant_max,float(abs(p.constant_support-p.drop_support).max()))
    k=pd.read_csv(OUT/"KBO2026_sinker_research.csv",dtype={"pitcher":str},float_precision="round_trip")
    assert len(k)==21 and k.n_ff.lt(100).sum()==17
    for name in ["SI_geometry","SI_physics"]:
        assert k.loc[k[name+"_outside_domain"],name+"_supported_research"].isna().all()
    gates=json.loads((OUT/"sinker_diagnostic_gates.json").read_text())
    assert si.arm_angle.ge(60).sum()==0 and monthly.arm_angle.ge(60).sum()==0
    assert all(g["high_slot_protection"]=="판정 불가" and not g["production_eligible"] for g in gates.values())
    result={"passed":True,"locked_input_and_code_files":len(lock["files"]),"prior_files_SHA_preserved":prior,
        "independent_metric_values":scalar_checks,"maximum_metric_difference_deg":maximum_metrics,
        "independent_paired_values_and_intervals":paired_checks,"independent_sinker_ridge_models":model_count,
        "maximum_independent_ridge_prediction_difference_deg":maximum_ridge,
        "constant_support_drop_reproduce_max_deg":constant_max,"monthly_same_player_split":True,
        "no_target_in_prediction_inputs":True,"high_slot_protection":"판정 불가",
        "production_changed":False,"new_confirmation":False,"KBO_accuracy_verified":False,"historical_full_raw_verified":False}
    save("verification.json",result)
    print("VERIFIED",scalar_checks,"metrics",paired_checks,"paired",model_count,"ridge",sum(prior.values()),"prior",flush=True)


if __name__=="__main__":
    main()
