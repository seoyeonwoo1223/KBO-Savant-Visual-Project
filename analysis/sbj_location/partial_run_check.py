"""Do equal-length TrackMan runs with some failing pairs (equal_length_partial) look misaligned?
Compares pitch-type-group agreement of accepted pairs and whether a +-1 shift fits better. Read-only.

    python analysis/sbj_location/partial_run_check.py [season] [out.json]
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis/trajectory_audit"))
import pa_flow_strict as s  # noqa: E402

season = int(sys.argv[1]) if len(sys.argv) > 1 else 2024
out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "analysis/sbj_location/results/partial_run_check.json"
vb, tm, games, _ = s.load(season)
pairs, _ = s.candidate_runs(vb, tm, games)
offset = s.season_offset(vb, tm, pairs)
vpos = {ix: i for i, ix in enumerate(vb.index)}; tpos = {ix: i for i, ix in enumerate(tm.index)}
vv, tv = vb.velocity_kmh.astype(float).to_numpy(), tm.rel_speed.astype(float).to_numpy()
vo, to = vb.outs_before.astype(float).to_numpy(), tm.outs_before.astype(float).to_numpy()
vg, tg = vb.pitch_type_kr.map(s.VB_GROUP).to_numpy(), tm.pitch_type_group.to_numpy()
ok_pair = lambda a, b: (np.abs(vv[a] - tv[b] - offset) <= s.TOL) & (vo[a] == to[b])
rows = []
for v_ix, t_ix in pairs:
    vi = np.array([vpos[x] for x in v_ix]); ti = np.array([tpos[x] for x in t_ix]); n = len(vi)
    if n != len(ti): continue
    ok = ok_pair(vi, ti)   # NaN velocity counts as a failed pair, as in pa_flow_strict
    shifts = [ok_pair(vi[max(0, -k):n - max(0, k)], ti[max(0, k):n - max(0, -k)]).mean() for k in (-1, 1) if n > 1]
    known = pd.notna(vg[vi])
    rows.append({"kind": "clean" if ok.all() else "partial", "n": n, "accepted": int(ok.sum()), "ok_frac": ok.mean(),
                 "shift_best": max(shifts) if shifts else np.nan, "grp_ok": int(((vg[vi] == tg[ti]) & ok & known).sum()), "grp_n": int((ok & known).sum())})
r = pd.DataFrame(rows); p = r[r.kind == "partial"]
agg = r.groupby("kind").agg(runs=("n", "size"), pitches=("n", "sum"), accepted=("accepted", "sum"), grp_ok=("grp_ok", "sum"), grp_n=("grp_n", "sum"))
agg["pitch_group_agreement"] = (agg.grp_ok / agg.grp_n).round(4)
shift = p[p.shift_best > p.ok_frac]
result = {"season": season, "velocity_offset_kmh": round(offset, 2), "by_kind": agg.drop(columns=["grp_ok", "grp_n"]).to_dict("index"),
          "partial_ok_fraction_quartiles": p.ok_frac.quantile([.25, .5, .75]).round(3).tolist(),
          "partial_runs_under_half_ok": {"runs": int((p.ok_frac < .5).sum()), "accepted_pitches": int(p[p.ok_frac < .5].accepted.sum())},
          "partial_runs_where_shift_fits_better": {"runs": int(len(shift)), "accepted_pitches": int(shift.accepted.sum()),
                                                   "pitch_group_agreement": round(shift.grp_ok.sum() / max(shift.grp_n.sum(), 1), 4)},
          "note": "Diagnostic only. Pitch-type group and velocity are not independent of each other; agreement does not prove identity."}
out.write_text(json.dumps(result, ensure_ascii=False, indent=1)); print(json.dumps(result, ensure_ascii=False, indent=1))
