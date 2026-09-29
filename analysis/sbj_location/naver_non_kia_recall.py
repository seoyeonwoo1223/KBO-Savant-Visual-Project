"""How many Naver bunt fouls in non-KIA home games did the TrackMan correction path catch? (read-only)

    PYTHONPATH=src python analysis/sbj_location/naver_non_kia_recall.py

Sample: results/naver_non_kia_W_sample_2020_2023.csv (30 random non-KIA home games per season, 2020 and 2023,
numpy default_rng(20260929) per season; drawn for the K4 check). Each Naver `W` is joined to VB with the KIA home
join (naver_kia_home_bunts.join) and classified against data/corrections/vb_bunt_foul_corrections.json. A VB `B`
left uncorrected is traced through the TrackMan selection rule (build_trackman_bunt_corrections.py) to the step
where it dropped out. Writes results/naver_non_kia_recall_2020_2023.{json,csv}.
"""
from __future__ import annotations

import csv, json, sys
from collections import Counter

import numpy as np
import pandas as pd

from naver_kia_home_bunts import join
from naver_queue_verify import ROOT, RESULTS, game_pitches
from visualbaseball.collector import CALL_CORRECTIONS
from visualbaseball.curated import load_rows

sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "analysis/trajectory_audit")]
import pa_flow_strict as pf  # noqa: E402
import trackman_harness as th  # noqa: E402

SAMPLE = RESULTS / "naver_non_kia_W_sample_2020_2023.csv"
COLS = ["pitch_id", "game_id", "pa_id", "inning", "inning_half", "batter_id", "pitcher_id", "pitch_number",
        "velocity_kmh", "pitch_call_code", "is_pa_terminal"]


def trackman_trace(season: int) -> tuple[dict, set]:
    """pitch_id -> why the TrackMan rule did not select it (same steps as season_entries)."""
    vb, tm, games, _ = pf.load(season)
    t = pd.DataFrame(load_rows(ROOT, "pitches", season, columns=["pitch_id", "vx0", "vy0", "vz0", "trajectory_valid", "is_pa_terminal"]))
    t = t.set_index("pitch_id").reindex(vb.pitch_id)
    ok = t.trajectory_valid.fillna(False).astype(bool).to_numpy()
    traj = np.sqrt(t.vx0.astype(float) ** 2 + t.vy0.astype(float) ** 2 + t.vz0.astype(float) ** 2).to_numpy() * 1.09728
    m, _, _, _ = th.run(vb, tm, games, pd.Series(np.where(ok, traj, np.nan), index=vb.index), per_game=True)
    partner = dict(zip(m.vi, m.ti)); terminal = t.is_pa_terminal.fillna(False).astype(bool).to_numpy()
    reason = {}
    for vi, pid in enumerate(vb.pitch_id):
        ti = partner.get(vi)
        if ti is None:
            reason[pid] = "trackman_pitch_unmatched"; continue
        if terminal[vi]:
            reason[pid] = "terminal_pa"; continue
        nvi = vi + 1
        if nvi >= len(vb) or vb.pa_id.iat[nvi] != vb.pa_id.iat[vi] or partner.get(nvi) != ti + 1:
            reason[pid] = "next_pitch_unmatched"; continue
        a, b = tm.iloc[ti], tm.iloc[ti + 1]
        reason[pid] = ("trackman_count_not_strike_plus_one" if (int(b.balls_before), int(b.strikes_before)) !=
                       (int(a.balls_before), int(a.strikes_before) + 1) else "selected_by_rule")
    return reason, set(tm.game_id)


def main() -> None:
    sample = list(csv.DictReader(SAMPLE.open(encoding="utf-8-sig")))
    table = json.loads(CALL_CORRECTIONS.read_text(encoding="utf-8"))["seasons"]
    rows, summary = [], {"definition": {"sample": SAMPLE.name, "join": "naver_kia_home_bunts.join (half-inning PA ordinal key)",
                                         "caveat": "Naver and VB may share an upstream source; this is a record cross-check, not an independent measurement"},
                         "seasons": {}}
    for season in (2020, 2023):
        games = [r["game_id"] for r in sample if r["season"] == str(season)]
        in_table = {e["pitch_id"]: e.get("source", "trackman") for e in table[str(season)]["pitches"]}
        vb_all = {}
        for r in load_rows(ROOT, "pitches", season, columns=COLS):
            if r["game_id"] in games:
                vb_all.setdefault(r["game_id"], []).append(r)
        trace, tm_games = trackman_trace(season)
        st, per_game = Counter(), {}
        for g in games:
            naver, failed = game_pitches(g)
            if failed:
                st["games_incomplete"] += 1; continue
            vb = vb_all.get(g, []); joined = join(vb, naver); by = {r["pitch_id"]: r for r in vb}
            back = {id(n): p for p, (s, n) in joined.items() if n is not None}
            per_game[g] = sum(n["code"] == "W" for n in naver)
            for n in naver:
                if n["code"] != "W":
                    continue
                pid = back.get(id(n)); v = by.get(pid) if pid else None
                call = str(v["pitch_call_code"]).upper() if v else ""
                if v is None:
                    outcome = "unjoined"
                elif pid in in_table:
                    outcome = f"corrected_{in_table[pid]}"
                elif call == "B":
                    outcome = "missed:" + ("game_not_in_trackman" if g not in tm_games else trace.get(pid, "not_traced"))
                else:
                    outcome = f"vb_recorded_{call}"
                st[outcome] += 1; st["naver_W"] += 1
                rows.append({"season": season, "game_id": g, "pitch_id": pid or "", "naver_pitch_id": n["pts_id"], "vb_call": call,
                             "naver_count_before": n["count_before"], "naver_count_after": n["count_after"],
                             "ends_pa": bool(v["is_pa_terminal"]) if v else "", "outcome": outcome})
        gpt = {r["game_id"]: int(r["W"]) for r in sample if r["season"] == str(season)}
        vb_b = st["naver_W"] - st["unjoined"] - sum(v for k, v in st.items() if k.startswith("vb_recorded_") and k != "vb_recorded_B")
        caught = sum(v for k, v in st.items() if k.startswith("corrected_"))
        summary["seasons"][str(season)] = {"games": len(games), "stats": dict(sorted(st.items())),
                                           "W_per_game_matches_sample_csv": per_game == gpt,
                                           "recall_of_vb_B_bunt_fouls": round(caught / vb_b, 3) if vb_b else None}
        print(season, json.dumps(summary["seasons"][str(season)], ensure_ascii=False), flush=True)
    (RESULTS / "naver_non_kia_recall_2020_2023.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    with (RESULTS / "naver_non_kia_recall_2020_2023.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


if __name__ == "__main__":
    main()
