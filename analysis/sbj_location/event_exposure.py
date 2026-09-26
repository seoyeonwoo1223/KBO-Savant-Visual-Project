"""Exposure of source-event quality signals to SBJ paths (2024-2026). Read-only."""
import json
import numpy as np, pandas as pd
from pathlib import Path
from visualbaseball.curated import load_rows
import sys
A = sys.argv[1]   # scripts/audit_sbj_data.py --out directory
W = Path(sys.argv[2])   # pzone_experiment.py work dir
ROOT = Path(__file__).resolve().parents[2]
out = {}
for s in (2024, 2025, 2026):
    q = pd.read_csv(f"{A}/sbj_pitch_quality_{s}.csv.gz", dtype={"pitch_id": str, "pa_id": str, "flags": str, "tm_event": str, "run_kind": str})
    e = pd.read_parquet(W / f"pzone_exp_{s}.parquet")[["pitch_id", "swing", "event", "batter_id"]]
    q = q.merge(e, on="pitch_id", how="left", indicator=True)
    q["eligible"] = q["_merge"].eq("both"); q["is_take"] = q.eligible & q.swing.eq(0)
    if "pitch_call_code" not in q.columns:
        q = q.merge(pd.DataFrame(load_rows(ROOT, "pitches", s, columns=["pitch_id","pitch_call_code"])), on="pitch_id", how="left")
    q["code"] = q.pitch_call_code.fillna("").str.upper()
    q["flag_list"] = q["flags"].fillna("").str.split(",")
    # pitches after a V in the same PA: count state inherits the uncounted V
    q = q.sort_values(["pa_id", "pitch_id"]); q["after_v"] = q.groupby("pa_id")["code"].transform(lambda c: c.eq("V").cumsum().shift(fill_value=0) > 0)
    qual = e.groupby("batter_id").size(); qual = set(qual[qual >= 300].index)
    def row(mask):
        m = q[mask]
        return {"vb_pitches": int(len(m)), "sbj_eligible": int(m.eligible.sum()), "pzone_target_takes": int(m["is_take"].sum()),
                "pswing_train_and_scored": int(m.eligible.sum()), "qualified_batters_touched": int(m[m.eligible].batter_id.isin(qual).groupby(m[m.eligible].batter_id).any().sum())}
    r = {"all": row(q.index == q.index), "review_structural": row(q.review_level.eq("structural")), "review_diagnostic": row(q.review_level.eq("diagnostic"))}
    for f in sorted({x for l in q.flag_list for x in l if x}):
        r[f"flag:{f}"] = row(q.flag_list.apply(lambda l: f in l))
    r["code_V"] = row(q.code.eq("V")); r["after_V_same_pa"] = row(q.after_v)
    r["code_B"] = row(q.code.eq("B"))
    if s == 2024:
        mt = q.match_status.eq("matched")
        r["tm_matched"] = row(mt); r["tm_unmatched"] = row(q.match_status.eq("unmatched"))
        r["tm_equal_length_partial"] = row(q.run_kind.eq("equal_length_partial"))
        r["tm_count_mismatch"] = row(q.count_mismatch.astype(str).eq("True"))
        r["tm_count_mismatch_in_partial"] = row(q.count_mismatch.astype(str).eq("True") & q.run_kind.eq("equal_length_partial"))
        r["tm_B_then_tm_strike"] = row(q.code.eq("B") & q.tm_event.eq("strike"))
        r["tm_V_matched"] = row(q.code.eq("V") & mt)
        r["unmatched_reasons"] = q[q.match_status.eq("unmatched")].unmatched_reason.value_counts().to_dict()
        r["unmatched_game_unmapped_KIA_home"] = int((q.unmatched_reason.eq("game_unmapped") & q.game_id.str[10:12].eq("HT")).sum())
    out[s] = r
json.dump(out, open(W / "event_exposure.json", "w"), ensure_ascii=False, indent=1)
for s, r in out.items():
    print("=====", s)
    for k, v in r.items(): print(f"  {k:32s} {v}")
