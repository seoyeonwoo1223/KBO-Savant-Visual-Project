"""등록한 두 싱커 앵커를 과거 학습·투수 분리 및 재사용 월에서 평가한다."""
from __future__ import annotations

import hashlib
import pickle

import numpy as np
import pandas as pd

from common import (OUT, SI_GEOMETRY, SI_PHYSICS, eligible_si, legacy_helpers,
                    load, metrics, paired, save, sha)

OPTIONS = {"SI_geometry": SI_GEOMETRY, "SI_physics": SI_PHYSICS}


def domain(training, test, columns):
    x = test[columns].to_numpy(float)
    lo, hi = training[columns].min().to_numpy(), training[columns].max().to_numpy()
    outside = (x < lo-1e-12) | (x > hi+1e-12) | ~np.isfinite(x)
    return outside.any(axis=1), [",".join(np.array(columns)[row]) for row in outside]


def predict(model, d, columns):
    assert "arm_angle" not in d
    return model.predict(d[columns].to_numpy(float))


def report(population, d, options, reference):
    statistics = {name: metrics(d, p) for name, p in {"reference": reference, **options}.items()}
    comparisons = {name: paired(d, reference, p) for name, p in options.items()}
    save(population+"_sinker_scores.json", {"population": population, "metrics": statistics,
        "paired_vs_reference": comparisons, "period_reused": True, "candidate_selected": False})
    rows = [{"population":population,"model":model,"group":group,**values}
            for model, groups in statistics.items() for group, values in groups.items()]
    pd.DataFrame(rows).to_csv(OUT/(population+"_sinker_metrics.csv"),index=False)
    return statistics


def diagnostic_gate(scores):
    b, result = scores["reference"], {}
    for model in OPTIONS:
        s = scores[model]
        conditions = {"SI50_support":s["all"]["players"]>=50,
            "MAE_gain0p10":s["all"]["MAE"]<=b["all"]["MAE"]-.1,
            "downside_gain0p10":s["all"]["downside"]<=b["all"]["downside"]-.1,
            "abs_bias_margin0p10":abs(s["all"]["bias"])<=abs(b["all"]["bias"])+.1}
        low = s["SI_IVB_le10"]
        conditions["low_IVB_support20"] = low["players"]>=20
        if low["players"]:
            conditions["low_IVB_downside_gain0p05"] = low["downside"]<=b["SI_IVB_le10"]["downside"]-.05
            conditions["low_IVB_abs_bias_margin0p10"] = abs(low["bias"])<=abs(b["SI_IVB_le10"]["bias"])+.1
        conditions["high60_support20"] = s["high60"]["players"]>=20
        if conditions["high60_support20"]:
            conditions["high60_MAE_margin0p25"] = s["high60"]["MAE"]<=b["high60"]["MAE"]+.25
            conditions["high60_negative_bias_margin0p25"] = s["high60"]["bias"]>=b["high60"]["bias"]-.25
        result[model] = {"conditions":conditions,"high_slot_protection":"판정 불가" if not conditions["high60_support20"] else "진단 가능",
                         "production_eligible":False,"new_confirmation":False}
    return result


def main():
    ridge_fit, _, _, _, _ = legacy_helpers()
    all_history = load("MLB",labelled=True)
    history = all_history.loc[eligible_si(all_history,True)].reset_index(drop=True)
    assert len(history)==198 and history.pitcher.nunique()==115
    assert history.groupby("pitcher").outer_fold.nunique().max()==1
    baseline = pd.read_parquet(OUT/"inputs/MLB_OOF_predictions_reference.parquet")
    joined = history.merge(baseline[["pitcher","season","anchor"]],on=["pitcher","season"],validate="one_to_one")
    reference = joined.anchor.to_numpy()
    oof = {name:np.full(len(history),np.nan) for name in OPTIONS}
    outside = {name:np.zeros(len(history),bool) for name in OPTIONS}
    models, audits, fold_rows = {}, [], []
    for fold in sorted(history.outer_fold.unique()):
        tr = history.loc[history.outer_fold.ne(fold)].copy()
        mask = history.outer_fold.eq(fold).to_numpy()
        va = history.loc[mask]
        assert set(tr.pitcher).isdisjoint(va.pitcher)
        models[int(fold)] = {}
        for name, columns in OPTIONS.items():
            model = ridge_fit(tr,columns)
            models[int(fold)][name] = {"model":model,"training":tr[["pitcher"]+columns].copy(),"columns":columns}
            oof[name][mask] = predict(model,va.drop(columns="arm_angle"),columns)
            outside[name][mask], _ = domain(tr,va,columns)
            for group, values in metrics(va,oof[name][mask]).items():
                fold_rows.append({"fold":int(fold),"model":name,"group":group,**values})
        audits.append({"fold":int(fold),"training_players":sorted(tr.pitcher.unique()),"validation_players":sorted(va.pitcher.unique()),
            "training_rows":len(tr),"validation_rows":len(va),"training_high60_rows":int(tr.arm_angle.ge(60).sum())})
    assert all(np.isfinite(p).all() for p in oof.values())
    table = history[["row_id","pitcher","season","primary4","n_ff","type_SI_count","type_SI_ivb_in","outer_fold","arm_angle"]].copy()
    table["reference"] = reference
    for name in OPTIONS:
        table[name] = oof[name]
        table[name+"_outside_domain"] = outside[name]
    table.to_parquet(OUT/"MLB_sinker_predictions.parquet",index=False)
    scores = report("MLB_OOF_reused",history,oof,reference)
    save("sinker_diagnostic_gates.json",diagnostic_gate(scores))
    pd.DataFrame(fold_rows).to_csv(OUT/"sinker_fold_metrics.csv",index=False)
    foldmap = all_history.groupby("pitcher").outer_fold.first().to_dict()
    monthly = []
    for month in ["May","July"]:
        d = load(month,labelled=True)
        d = d.loc[eligible_si(d,True)].reset_index(drop=True)
        d["evaluation_fold"] = [int(foldmap[p]) if p in foldmap else int(hashlib.sha256(p.encode()).hexdigest(),16)%5 for p in d.pitcher]
        for name, columns in OPTIONS.items():
            d[name] = np.nan
            d[name+"_outside_domain"] = False
            for fold in range(5):
                mask = d.evaluation_fold.eq(fold)
                bundle = models[fold][name]
                assert set(d.loc[mask,"pitcher"]).isdisjoint(bundle["training"].pitcher)
                inputs = d.loc[mask].drop(columns="arm_angle")
                d.loc[mask,name] = predict(bundle["model"],inputs,columns)
                flags, _ = domain(bundle["training"],inputs,columns)
                d.loc[mask,name+"_outside_domain"] = flags
        refs = pd.read_parquet(OUT/f"inputs/{month}_references.parquet")
        d = d.merge(refs[["row_id","v1_MLB_direct_component"]],on="row_id",validate="one_to_one")
        d["reference"] = d.v1_MLB_direct_component
        d["month"] = month
        d[["row_id","pitcher","season","month","primary4","n_ff","type_SI_count","type_SI_ivb_in","evaluation_fold","arm_angle","reference"]
          +list(OPTIONS)+[n+"_outside_domain" for n in OPTIONS]].to_parquet(OUT/(month+"_sinker_predictions.parquet"),index=False)
        report(month+"2025_reused",d,{n:d[n].to_numpy() for n in OPTIONS},d.reference.to_numpy())
        monthly.append(d)
    combined = pd.concat(monthly,ignore_index=True)
    report("MayJuly2025_reused",combined,{n:combined[n].to_numpy() for n in OPTIONS},combined.reference.to_numpy())

    fixed = {name:ridge_fit(history,columns) for name,columns in OPTIONS.items()}
    k = load("KBO_all")
    k = k.loc[eligible_si(k)].reset_index(drop=True)
    assert len(k)==21
    kt = k[["row_id","pitcher","season","name","primary4","n_ff","type_SI_count"]].copy()
    for name, columns in OPTIONS.items():
        kt[name+"_raw"] = predict(fixed[name],k,columns)
        flags, reason = domain(history,k,columns)
        kt[name+"_outside_domain"] = flags
        kt[name+"_outside_features"] = reason
        kt[name+"_supported_research"] = kt[name+"_raw"].where(~flags)
    kt.to_csv(OUT/"KBO2026_sinker_research.csv",index=False)
    # 같은 지지영역 공통 행의 민감도 보고는 raw 전체 비교와 별도로 남긴다.
    domain_report = {}
    for name in OPTIONS:
        domain_report[name] = {"MLB_oof_outside_rows":int(outside[name].sum()),
            "monthly_outside_rows":int(combined[name+"_outside_domain"].sum()),
            "KBO_supported_players":int((~kt[name+"_outside_domain"]).sum())}
        common = ~outside[name]
        save(name+"_MLB_common_domain.json",{"common_rows":int(common.sum()),"reference":metrics(history.loc[common],reference[common]),
            "candidate":metrics(history.loc[common],oof[name][common]),"shared_cohort":True})
    with (OUT/"sinker_models.pkl").open("wb") as f:
        pickle.dump({"fold_models":models,"fixed_models":fixed,"columns":OPTIONS},f)
    save("sinker_audit.json",{"definition_sha256":sha(OUT/"gates.md"),"code_sha256":sha(__file__),
        "outer_splits":audits,"monthly_same_player_fold":True,"monthly_not_used_for_training":True,
        "domain":domain_report,"KBO_reference_angles_used":False,"high60_training_rows":int(history.arm_angle.ge(60).sum()),
        "operational_changed":False,"new_confirmation":False,"model_selected":False})
    print("SINKER_DONE",len(history),history.pitcher.nunique(),len(combined),combined.pitcher.nunique(),len(k),flush=True)


if __name__ == "__main__":
    main()
