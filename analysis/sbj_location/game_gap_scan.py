"""Games where VB has far fewer pitches than first-team TrackMan in the same half-innings (read-only).

    python analysis/sbj_location/game_gap_scan.py <out csv>

Uses the PR #29 game mapping (scripts/build_trackman_id_crosswalk.py map_games). Per half-inning it
compares VB pitch counts with TrackMan pitch counts; TrackMan is a reference, not ground truth.
"""
import importlib.util, sys
from pathlib import Path
import pandas as pd
from visualbaseball.curated import load_rows

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("cw", ROOT / "scripts/build_trackman_id_crosswalk.py")
cw = importlib.util.module_from_spec(spec); spec.loader.exec_module(cw)
rows = []
for season in range(2019, 2025):
    tm = cw._trackman(ROOT, season); vbp = cw._visualbaseball(ROOT, season)
    games = cw.map_games(tm, vbp)
    vb = pd.DataFrame(load_rows(ROOT, "pitches", season, columns=["game_id", "inning", "inning_half"]))
    vbc = vb.groupby(["game_id", "inning", "inning_half"]).size().rename("vb")
    t = tm[tm.trackman_game_id.isin(games)].copy(); t["game_id"] = t.trackman_game_id.map(games)
    tmc = t.groupby(["game_id", "inning", "half"]).size().rename("tm"); tmc.index.names = vbc.index.names
    j = pd.concat([vbc, tmc], axis=1).fillna(0).astype(int).reset_index()
    j["short"] = (j.tm - j.vb).clip(lower=0)
    g = j.groupby("game_id").agg(vb=("vb", "sum"), tm=("tm", "sum"), short=("short", "sum"),
                                 halves_short_ge5=("short", lambda s: int((s >= 5).sum())))
    g["season"] = season; rows.append(g.reset_index())
r = pd.concat(rows)
out = r[(r.short >= 15) | (r.halves_short_ge5 >= 2)].sort_values("short", ascending=False)
out.to_csv(sys.argv[1], index=False)
print("mapped games:", len(r), " flagged:", len(out))
print(out.groupby("season").size().to_dict())
print(out.head(15).to_string(index=False))
