"""기존 R2를 재현하고 standalone 지원값만 제거·고정한다."""
from __future__ import annotations

import pickle

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from common import (OUT, FF, EXTRA, BASE_SEED, legacy_helpers, load,
                    metrics, paired, save, sha)

RIDGE_FIT, WEIGHTS, BASE, FIT_PROJECTION, APPLY_PROJECTION = (None,)*5
SUPPORT = EXTRA.index("game_pair_support")
VARIANTS = ["full","drop_support","constant_support"]
QUANTILES = {"support_q10":.1,"support_q50":.5,"support_q90":.9}


def groups(d):
    from run_eaa_low_ivb_20261006 import masks
    result = masks(d)
    result.update({name:d.primary4.eq(name).to_numpy() for name in ["FF","SI"]})
    return {name:np.asarray(mask,bool) for name,mask in result.items()}


def prepare(d):
    oof, splits = np.full(len(d),np.nan), []
    for tr,va in GroupKFold(3,shuffle=True,random_state=BASE_SEED).split(d,groups=d.pitcher):
        assert set(d.iloc[tr].pitcher).isdisjoint(d.iloc[va].pitcher)
        anchor = RIDGE_FIT(d.iloc[tr],FF)
        oof[va] = anchor.predict(d.iloc[va][FF].to_numpy(float))
        splits.append({"training_players":sorted(d.iloc[tr].pitcher.unique()),"validation_players":sorted(d.iloc[va].pitcher.unique())})
    return {"anchor":RIDGE_FIT(d,FF),"target":d.arm_angle.to_numpy()-oof,
            "weights":WEIGHTS(d),"splits":splits,"training_players":sorted(d.pitcher.unique())}


def fit(d,shared,variant):
    indices = [i for i in range(len(EXTRA)) if variant!="drop_support" or i!=SUPPORT]
    raw = d[EXTRA].to_numpy(float)[:,indices].copy()
    support = d.game_pair_support.to_numpy(float)
    constant = float(np.median(support))
    if variant=="constant_support":raw[:,indices.index(SUPPORT)] = constant
    medians = np.array([np.median(c[np.isfinite(c)]) if np.isfinite(c).any() else 0 for c in raw.T])
    filled = np.where(np.isfinite(raw),raw,medians)
    w, target = shared["weights"], shared["target"]
    projection,r = FIT_PROJECTION(BASE(d),filled,w)
    rows, targets, groups = [], [], []
    for g in ["FF","SI","FC","OTHER"]:
        mask = d.primary4.eq(g).to_numpy()
        count = d.loc[mask].pitcher.nunique()
        if count<20:continue
        rows.append(np.average(r[mask],axis=0,weights=w[mask]))
        targets.append(np.average(target[mask],weights=w[mask]))
        groups.append({"primary4":g,"players":int(count)})
    gm, gt = np.array(rows),np.array(targets)
    mass = w.sum()/max(1,len(rows))
    gram = r.T@(w[:,None]*r)+300*np.eye(r.shape[1])+mass*gm.T@gm
    rhs = r.T@(w*target)+mass*gm.T@gt
    coef = np.linalg.solve(gram,rhs)
    return {"anchor":shared["anchor"],"indices":indices,"medians":medians,"projection":projection,
        "coef":coef,"variant":variant,"constant":constant,
        "quantiles":{k:float(np.quantile(support,q)) for k,q in QUANTILES.items()},
        "normal_equation_max_error":float(abs(gram@coef-rhs).max()),"group_support":groups,
        "training_players":shared["training_players"],"inner_splits":shared["splits"]}


def predict(model,d,scenario=None):
    assert "arm_angle" not in d
    raw = d[EXTRA].to_numpy(float)[:,model["indices"]].copy()
    if scenario or model["variant"]=="constant_support":
        raw[:,model["indices"].index(SUPPORT)] = model["quantiles"][scenario] if scenario else model["constant"]
    filled = np.where(np.isfinite(raw),raw,model["medians"])
    r = APPLY_PROJECTION(model["projection"],BASE(d),filled)
    delta_raw = r@model["coef"]
    baseline = model["anchor"].predict(d[FF].to_numpy(float))
    return baseline+5*np.tanh(delta_raw/5),delta_raw,r


def evaluation(population,d,predictions):
    masks = groups(d)
    statistics = {name:metrics(d,p,masks) for name,p in predictions.items()}
    comparisons = {name:paired(d,predictions["full"],p,masks) for name,p in predictions.items() if name not in ["full","anchor"]}
    save(population+"_support_scores.json",{"population":population,"metrics":statistics,"paired_vs_full":comparisons,
        "period_reused":True,"candidate_selected":False})
    pd.DataFrame([{"population":population,"model":model,"group":group,**values}
        for model,groups in statistics.items() for group,values in groups.items()]).to_csv(OUT/(population+"_support_metrics.csv"),index=False)


def main():
    global RIDGE_FIT, WEIGHTS, BASE, FIT_PROJECTION, APPLY_PROJECTION
    RIDGE_FIT, WEIGHTS, BASE, FIT_PROJECTION, APPLY_PROJECTION = legacy_helpers()
    d = load("MLB",labelled=True)
    masks = groups(d)
    names = ["anchor"]+VARIANTS+list(QUANTILES)
    oof = {name:np.full(len(d),np.nan) for name in names}
    audits, folds, models = [], [], {}
    for fold in sorted(d.outer_fold.unique()):
        tr = d.loc[d.outer_fold.ne(fold)].reset_index(drop=True)
        mask = d.outer_fold.eq(fold).to_numpy()
        va = d.loc[mask]
        assert set(tr.pitcher).isdisjoint(va.pitcher)
        shared = prepare(tr)
        fitted = {name:fit(tr,shared,name) for name in VARIANTS}
        inputs = va.drop(columns="arm_angle")
        oof["anchor"][mask] = shared["anchor"].predict(inputs[FF].to_numpy(float))
        for name in VARIANTS:oof[name][mask] = predict(fitted[name],inputs)[0]
        for scenario in QUANTILES:oof[scenario][mask] = predict(fitted["full"],inputs,scenario)[0]
        difference = float(abs(oof["constant_support"][mask]-oof["drop_support"][mask]).max())
        assert difference<1e-8
        models[int(fold)] = fitted
        audits.append({"fold":int(fold),"training_players":sorted(tr.pitcher.unique()),"validation_players":sorted(va.pitcher.unique()),
            "inner_splits":shared["splits"],"constant_drop_max_deg":difference,
            "variants":{name:{"medians":model["medians"],"indices":model["indices"],"projection_keep":model["projection"]["keep"],
                "normal_equation_max_error":model["normal_equation_max_error"],"support_constant":model["constant"],
                "support_quantiles":model["quantiles"]} for name,model in fitted.items()}})
        for name in names:
            for group,values in metrics(va,oof[name][mask],{g:m[mask] for g,m in masks.items()}).items():
                folds.append({"fold":int(fold),"model":name,"group":group,**values})
        print("SUPPORT_OUTER_DONE",int(fold),flush=True)
    old = pd.read_parquet(OUT/"inputs/MLB_OOF_predictions_reference.parquet")
    assert d[["pitcher","season"]].equals(old[["pitcher","season"]])
    diffs = {"MLB_anchor":float(abs(oof["anchor"]-old.anchor).max()),"MLB_full":float(abs(oof["full"]-old.full).max())}
    assert max(diffs.values())<1e-8
    pred = d[["row_id","pitcher","season","primary4","n_ff","type_SI_ivb_in","outer_fold","arm_angle"]].copy()
    for name,p in oof.items():pred[name]=p
    pred.to_parquet(OUT/"MLB_support_predictions.parquet",index=False)
    evaluation("MLB_OOF_reused",d,oof)
    pd.DataFrame(folds).to_csv(OUT/"support_fold_metrics.csv",index=False)
    train = d.loc[d.fixed_training_row].reset_index(drop=True)
    shared = prepare(train)
    fixed = {name:fit(train,shared,name) for name in VARIANTS}
    for population in ["May","July","KBO_FF100"]:
        label = population!="KBO_FF100"
        frame = load(population,labelled=label)
        if label:frame=frame.loc[frame.FF100_evaluation_eligible].reset_index(drop=True)
        inputs = frame.drop(columns="arm_angle",errors="ignore")
        predictions = {"anchor":shared["anchor"].predict(inputs[FF].to_numpy(float))}
        for name in VARIANTS:predictions[name]=predict(fixed[name],inputs)[0]
        for name in QUANTILES:predictions[name]=predict(fixed["full"],inputs,name)[0]
        legacy_file = {"May":"May2025_reused","July":"July2025_reused","KBO_FF100":"KBO2026"}[population]
        legacy = pd.read_parquet(OUT/f"inputs/{legacy_file}_predictions_reference.parquet")
        assert frame[["pitcher","season"]].equals(legacy[["pitcher","season"]])
        diffs[population+"_anchor"] = float(abs(predictions["anchor"]-legacy.anchor).max())
        diffs[population+"_full"] = float(abs(predictions["full"]-legacy.full).max())
        assert max(diffs.values())<1e-8
        tab = frame[["row_id","pitcher","season","primary4"]+(["arm_angle"] if label else [])].copy()
        for name,p in predictions.items():tab[name]=p
        tab.to_csv(OUT/(population+"_support_predictions.csv"),index=False)
        assert float(abs(predictions["constant_support"]-predictions["drop_support"]).max())<1e-8
        if label:evaluation(population+"2025_reused",frame,predictions)
    kbo = pd.read_csv(OUT/"KBO_FF100_support_predictions.csv",dtype={"pitcher":str},float_precision="round_trip")
    kbo = kbo.merge(load("KBO_all")[["pitcher","name"]],on="pitcher",validate="one_to_one")
    focus = kbo.loc[kbo.name.isin(["전준표","박준현","안우진","손주영","문동주"])].copy()
    for name in names:
        if name!="anchor":focus[name+"_delta_vs_anchor"]=focus[name]-focus.anchor
    focus.to_csv(OUT/"KBO_focus_support.csv",index=False)
    with (OUT/"support_models.pkl").open("wb") as handle:pickle.dump({"outer":models,"fixed":fixed},handle)
    save("support_audit.json",{"definition_sha256":sha(OUT/"gates.md"),"code_sha256":sha(__file__),"outer_splits":audits,
        "fixed_training_players":shared["training_players"],"fixed_inner_splits":shared["splits"],
        "historical_prediction_reproduction_max_deg":diffs,"standalone_support_only":True,
        "other_game_covariance_support_weighting_preserved":True,"model_selected":False,"production_changed":False,"new_confirmation":False})
    print("SUPPORT_DONE",max(diffs.values()),flush=True)


if __name__ == "__main__":
    main()
