"""List pitches that should exist but are missing from VB, as targets for an external relay lookup (read-only).

    python analysis/sbj_location/missing_pitch_targets.py <out csv>

Two sources:
- `captured`: pitches confirmed missing by user captures/video (results/case*_correspondence.csv, vb_row == '없음').
- `half_short`: every TrackMan pitch in a half-inning where VB has fewer pitches than TrackMan, for the games in
  results/game_gap_scan.csv. TrackMan is a reference (order, count, speed, type), not ground truth, and has no
  plate location. VB ids come from the player crosswalk, else the TrackMan id when VB uses the same id.
"""
import importlib.util, json, sys
from pathlib import Path
import pandas as pd
from visualbaseball.curated import load_rows

ROOT = Path(__file__).resolve().parents[2]; RES = ROOT / "analysis/sbj_location/results"
spec = importlib.util.spec_from_file_location("cw", ROOT / "scripts/build_trackman_id_crosswalk.py")
cw = importlib.util.module_from_spec(spec); spec.loader.exec_module(cw)
xw = json.loads((ROOT / "data/tracking/player_id_crosswalk.json").read_text(encoding="utf-8"))
out = []
gaps = pd.read_csv(RES / "game_gap_scan.csv", dtype={"game_id": str})
for season, gg in gaps.groupby("season"):
    tm = cw._trackman(ROOT, season); games = cw.map_games(tm, cw._visualbaseball(ROOT, season))
    inv = {v: k for k, v in games.items()}
    vb = pd.DataFrame(load_rows(ROOT, "pitches", season, columns=["game_id", "inning", "inning_half", "batter_id", "batter_name", "pitcher_id", "pitcher_name"]))
    names = {**dict(zip(vb.batter_id.astype(str), vb.batter_name)), **dict(zip(vb.pitcher_id.astype(str), vb.pitcher_name))}
    look = {role: {p["trackman_id"]: p["visualbaseball_id"] for p in xw["seasons"][str(season)]["roles"][role]["pairs"]} for role in ("pitcher", "batter")}
    for gid in gg.game_id:
        t = tm[tm.trackman_game_id == inv[gid]].copy()
        v = vb[vb.game_id == gid].groupby(["inning", "inning_half"]).size()
        t["vb_half_pitches"] = [int(v.get((i, h), 0)) for i, h in zip(t.inning, t.half)]
        t["tm_half_pitches"] = t.groupby(["inning", "half"]).pitch_no.transform("size")
        t = t[t.tm_half_pitches > t.vb_half_pitches].sort_values("pitch_no")
        for _, r in t.iterrows():
            pid = look["pitcher"].get(r.pitcher_trackman_id, r.pitcher_trackman_id); bid = look["batter"].get(r.batter_trackman_id, r.batter_trackman_id)
            out.append({"source": "half_short", "season": season, "game_id": gid, "game_date": r.date, "inning": int(r.inning), "half": r.half,
                        "pitcher_vb_id": pid, "pitcher_name": names.get(pid, ""), "batter_vb_id": bid, "batter_name": names.get(bid, ""),
                        "pitch_of_pa": int(r.pitch_of_pa), "count_before": f"{int(r.balls_before)}-{int(r.strikes_before)}", "outs_before": int(r.outs_before),
                        "tm_speed_kmh": r.rel_speed, "tm_type": r.tagged_pitch_type, "known_call": "", "known_speed_kmh": "", "known_type": "",
                        "vb_half_pitches": int(r.vb_half_pitches), "tm_half_pitches": int(r.tm_half_pitches), "tm_pitch_no": int(r.pitch_no), "evidence": "TrackMan"})
for f in sorted(RES.glob("case*_correspondence.csv")) + [RES / "kim_lim_20250809_correspondence.csv"]:
    c = pd.read_csv(f, dtype=str)
    if "vb_row" not in c: continue
    for _, r in c[c.vb_row.eq("없음")].iterrows():
        gid = next(p.stem.split("_")[1] for p in [f])
        out.append({"source": "captured", "season": int(gid[:4]), "game_id": gid, "game_date": gid[:8], "pa_label": r.pa, "pitch_of_pa": r.real_pitch_no,
                    "count_before": r.true_count_before, "known_call": r.real_call, "known_speed_kmh": r.real_speed_kmh, "known_type": r.real_type, "evidence": r.evidence})
df = pd.DataFrame(out); df.to_csv(sys.argv[1], index=False)
print(df.groupby(["source", "game_id"]).size().to_string())
