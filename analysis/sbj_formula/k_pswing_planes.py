"""K-A: ABS 시즌 p_swing에 판정면 입력(PZONE_ABS) 추가 (gates.md K). python analysis/sbj_formula/k_pswing_planes.py 2024

기준은 za7.3 투구 근거(data/metrics/zone_awareness/<Y>/pitches.parquet)다. 하네스는 za7.3 설정을 그대로 쓰고
p_swing 입력만 바꾼다. 결과: results/k_<season>.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).parent))
import sbj_exp as E  # noqa: E402
from c0c_calibration import ece  # noqa: E402
from visualbaseball import zone_decision as zd  # noqa: E402

ROOT = E.ROOT
OUT = Path(__file__).with_name("results")


def stats(df):
    side = df.p_zone >= .5
    r = 100 * (df.swing - df.p_swing)
    return {"league_sbj": float(100 * df.judgment.mean()),
            "residual_in": float(r[side].mean()), "residual_out": float(r[~side].mean()),
            "pswing_log_loss": float(E.bernoulli_loss(df.swing, df.p_swing).mean()),
            "pswing_ece": ece(df.swing, df.p_swing), "block_reproducibility": E.block_reproducibility(df)}


def main():
    y = int(sys.argv[1]); rows = E.rows_for(y); fields = zd.pzone_fields(y)
    ev = pq.read_table(ROOT / f"data/metrics/zone_awareness/{y}/pitches.parquet", columns=["game_id", "p_swing", "p_zone"]).to_pandas()
    ordered, fold, _ = E.ordered_folds(rows)
    assert [r["game_id"] for r in ordered] == ev.game_id.tolist()
    base = E.frame({"rows": ordered, "fold": fold, "p_swing": ev.p_swing.to_numpy(), "p_zone": ev.p_zone.to_numpy()})
    original = zd.NUMERIC
    zd.NUMERIC = original + tuple(zd.PZONE_ABS)
    try:
        res = E.crossfit(rows, fields, pswing_es=False, calibration="always", pzone_seeds=zd.PZONE_SEEDS)
    finally:
        zd.NUMERIC = original
    assert np.allclose(res["p_zone"], base.p_zone)  # p_zone은 za7.3 그대로
    cand = E.frame(res)
    sb, sc = E.player_sbj(base), E.player_sbj(cand)
    rb, rc = sb.rank(ascending=False, method="min"), sc[sb.index].rank(ascending=False, method="min")
    shift = (rb - rc).abs()
    b, c = stats(base), stats(cand)
    out = {"season": y, "za73": b, "k_a": c, "seconds": res["seconds"],
           "players": {"qualified": len(sb), "mean_abs_delta": float((sc[sb.index] - sb).abs().mean()),
                       "max_abs_delta": float((sc[sb.index] - sb).abs().max()), "signed_mean_delta": float((sc[sb.index] - sb).mean()),
                       "spearman": float(sb.rank().corr(sc[sb.index].rank())), "max_rank_shift": int(shift.max()),
                       "moved_5_or_more": int((shift >= 5).sum())},
           "gates": {"K1": {"value": c["league_sbj"], "pass": abs(c["league_sbj"]) <= .10},
                     "K2": {"in": c["residual_in"], "out": c["residual_out"], "pass": abs(c["residual_in"]) <= .15 and abs(c["residual_out"]) <= .15},
                     "K3": {"candidate": c["pswing_log_loss"], "za73": b["pswing_log_loss"], "pass": c["pswing_log_loss"] <= b["pswing_log_loss"]},
                     "K4": {"candidate": c["pswing_ece"], "za73": b["pswing_ece"], "pass": c["pswing_ece"] <= b["pswing_ece"] + .001}}}
    out["gates"]["pass"] = all(g["pass"] for g in out["gates"].values())
    (OUT / f"k_{y}.json").write_text(json.dumps(out, indent=1) + "\n")
    print(y, json.dumps(out["gates"]), json.dumps(out["players"]), flush=True)


if __name__ == "__main__":
    main()
