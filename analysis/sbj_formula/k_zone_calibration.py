"""K-B: p_swing 등위 보정을 존 안/밖으로 나눠 적합 (gates.md K-B). python analysis/sbj_formula/k_zone_calibration.py 2024

기준은 za7.3 투구 근거다. p_swing 모델·p_zone은 za7.3 그대로이고 보정만 바꾼다. 결과: results/kb_<season>.json
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import GroupKFold

sys.path.insert(0, str(Path(__file__).parent))
import sbj_exp as E  # noqa: E402
from k_pswing_planes import stats  # noqa: E402
from visualbaseball import zone_decision as zd  # noqa: E402

ROOT = E.ROOT
OUT = Path(__file__).with_name("results")


def iso():
    return IsotonicRegression(out_of_bounds="clip", y_min=1e-6, y_max=1 - 1e-6)


def zone_calibrated_pswing(train, test, test_in, fields):
    sa, sb = zd.encode(train, test, zd.PSWING_CATEGORICAL)
    actions = np.array([r["decision_type"] == "Swing" for r in train], dtype=int)
    raw = zd.fit_model(zd.pswing_classifier(), sa, actions).predict_proba(sb)[:, 1]
    groups = np.array([r["game_id"] for r in train])
    oof = np.empty(len(train)); train_in = np.empty(len(train), dtype=bool)
    for fit, held in GroupKFold(3).split(sa, actions, groups):
        oof[held] = zd.fit_model(zd.pswing_classifier(), sa[fit], actions[fit]).predict_proba(sa[held])[:, 1]
        train_in[held] = E.pzone_fit_predict([train[i] for i in fit], [train[i] for i in held], fields, zd.PZONE_SEEDS, "auto") >= .5
    p = iso().fit(oof, actions).predict(raw)  # 한쪽이 한 가지 행동뿐일 때의 대체값
    used = []
    for side in (True, False):
        m = train_in == side
        if len(set(actions[m])) == 2:
            t = test_in == side
            p[t] = iso().fit(oof[m], actions[m]).predict(raw[t]); used.append(side)
    return p, used


def main():
    y = int(sys.argv[1]); rows = E.rows_for(y); fields = zd.pzone_fields(y)
    ev = pq.read_table(ROOT / f"data/metrics/zone_awareness/{y}/pitches.parquet", columns=["game_id", "p_swing", "p_zone"]).to_pandas()
    ordered, fold, blocks = E.ordered_folds(rows)
    assert [r["game_id"] for r in ordered] == ev.game_id.tolist()
    base = E.frame({"rows": ordered, "fold": fold, "p_swing": ev.p_swing.to_numpy(), "p_zone": ev.p_zone.to_numpy()})
    p_swing = np.empty(len(ordered)); start = 0; t0 = time.time(); used = []
    for f, held in enumerate(blocks):
        train = [r for r in rows if r["game_id"][:8] not in held]
        n = int((fold == f).sum()); test = ordered[start:start + n]; sl = slice(start, start + n); start += n
        p_swing[sl], u = zone_calibrated_pswing(train, test, ev.p_zone.to_numpy()[sl] >= .5, fields); used.append(u)
    cand = E.frame({"rows": ordered, "fold": fold, "p_swing": p_swing, "p_zone": ev.p_zone.to_numpy()})
    sb, sc = E.player_sbj(base), E.player_sbj(cand)
    rb, rc = sb.rank(ascending=False, method="min"), sc[sb.index].rank(ascending=False, method="min")
    shift = (rb - rc).abs(); b, c = stats(base), stats(cand)
    out = {"season": y, "za73": b, "k_b": c, "seconds": time.time() - t0, "sides_calibrated": used,
           "players": {"qualified": len(sb), "mean_abs_delta": float((sc[sb.index] - sb).abs().mean()),
                       "max_abs_delta": float((sc[sb.index] - sb).abs().max()), "signed_mean_delta": float((sc[sb.index] - sb).mean()),
                       "spearman": float(sb.rank().corr(sc[sb.index].rank())), "max_rank_shift": int(shift.max()),
                       "moved_5_or_more": int((shift >= 5).sum())},
           "gates": {"K1": {"value": c["league_sbj"], "pass": abs(c["league_sbj"]) <= .10},
                     "K2": {"in": c["residual_in"], "out": c["residual_out"], "pass": abs(c["residual_in"]) <= .15 and abs(c["residual_out"]) <= .15},
                     "K3": {"candidate": c["pswing_log_loss"], "za73": b["pswing_log_loss"], "pass": c["pswing_log_loss"] <= b["pswing_log_loss"]},
                     "K4": {"candidate": c["pswing_ece"], "za73": b["pswing_ece"], "pass": c["pswing_ece"] <= b["pswing_ece"] + .001}}}
    out["gates"]["pass"] = all(g["pass"] for g in out["gates"].values())
    (OUT / f"kb_{y}.json").write_text(json.dumps(out, indent=1) + "\n")
    print(y, json.dumps(out["gates"]), json.dumps(out["players"]), flush=True)


if __name__ == "__main__":
    main()
