"""What does VB code V (bunt swing-and-miss per Naver 2025-2026) do to the TrackMan count? (read-only)

    python analysis/sbj_location/v_code_trackman.py <out json> [seasons...]

For each non-terminal VB `V` matched 1:1 to TrackMan (same alignment as scripts/build_trackman_bunt_corrections.py),
with the next VB pitch of the plate appearance matched to the next TrackMan pitch, record the TrackMan count change.
"""
import json, sys
from collections import Counter
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis/trajectory_audit")); sys.path.insert(0, str(ROOT / "analysis/sbj_location"))
import pa_flow_strict as pf  # noqa: E402
import trackman_harness as th  # noqa: E402
from visualbaseball.curated import load_rows  # noqa: E402

res = {}
for season in [int(s) for s in sys.argv[2:]] or list(range(2019, 2025)):
    vb, tm, games, _ = pf.load(season)
    t = pd.DataFrame(load_rows(ROOT, "pitches", season, columns=["pitch_id", "vx0", "vy0", "vz0", "trajectory_valid", "is_pa_terminal"]))
    t = t.set_index("pitch_id").reindex(vb.pitch_id)
    ok = t.trajectory_valid.fillna(False).astype(bool).to_numpy()
    traj = np.sqrt(t.vx0.astype(float) ** 2 + t.vy0.astype(float) ** 2 + t.vz0.astype(float) ** 2).to_numpy() * 1.09728
    m, _, _, _ = th.run(vb, tm, games, pd.Series(np.where(ok, traj, np.nan), index=vb.index), per_game=True)
    partner = dict(zip(m.vi, m.ti))
    code = vb.pitch_call_code.fillna("").str.upper().to_numpy()
    terminal = t.is_pa_terminal.fillna(False).astype(bool).to_numpy()
    c = Counter()
    for vi in np.flatnonzero(code == "V"):
        if terminal[vi]:
            c["terminal"] += 1; continue
        ti = partner.get(vi)
        if ti is None:
            c["unmatched"] += 1; continue
        if vi + 1 >= len(vb) or vb.pa_id.iat[vi + 1] != vb.pa_id.iat[vi] or partner.get(vi + 1) != ti + 1:
            c["next_not_matched"] += 1; continue
        a, b = tm.iloc[ti], tm.iloc[ti + 1]
        db, ds = int(b.balls_before) - int(a.balls_before), int(b.strikes_before) - int(a.strikes_before)
        c["strike" if (db, ds) == (0, 1) else "none_at_2_strikes" if (db, ds) == (0, 0) and int(a.strikes_before) == 2
          else "ball" if (db, ds) == (1, 0) else f"other_{db}_{ds}"] += 1
    res[season] = {"V": int((code == "V").sum()), **dict(c)}
    print(season, res[season], flush=True)
Path(sys.argv[1]).write_text(json.dumps(res, indent=1))
