"""Where do 2024 TrackMan count mismatches start? Read-only, uses the PR #29 audit ledger.

    python analysis/sbj_location/count_mismatch_origin.py <audit dir> <work dir>
"""
import json, sys
from pathlib import Path
import pandas as pd

A, W = Path(sys.argv[1]), Path(sys.argv[2])
q = pd.read_csv(A / "sbj_pitch_quality_2024.csv.gz", dtype=str).sort_values(["pa_id", "pitch_id"])
q["pn"] = q.pitch_id.str[-2:].astype(int); q["code"] = q.pitch_call_code.fillna("").str.upper()
g = q.groupby("pa_id")
q["prev_code"], q["prev_tm"], q["prev_cm"] = g.code.shift(), g.tm_event.shift(), g.count_mismatch.shift()
cm = q[q.count_mismatch.eq("True")].copy()


def cause(r):
    if r.pn == 1: return "vb_first_pitch_but_tm_not_0_0"
    if r.prev_cm == "True": return "propagated_from_previous_pitch"
    if r.prev_code == "B" and r.prev_tm == "strike": return "previous_vb_B_tm_strike"
    if r.prev_code == "V": return "previous_vb_V"
    if pd.isna(r.prev_tm) or r.prev_tm == "": return "previous_pitch_unlinked"
    return f"other_prev_{r.prev_code}_{r.prev_tm}"


cm["cause"] = cm.apply(cause, axis=1)
origin = cm[cm.prev_cm.ne("True")]
result = {"matched_candidates": int(q.match_status.eq("matched").sum()), "count_mismatch": int(len(cm)),
          "by_run_kind": cm.run_kind.value_counts().to_dict(),
          "by_cause": cm.cause.value_counts().to_dict(), "origin_pitches": int(len(origin)),
          "origin_by_cause": origin.cause.value_counts().to_dict(),
          "cause_by_run_kind": pd.crosstab(cm.cause, cm.run_kind).to_dict("index")}
(W / "count_mismatch_origin_2024.json").write_text(json.dumps(result, ensure_ascii=False, indent=1))
print(json.dumps(result, ensure_ascii=False, indent=1))
