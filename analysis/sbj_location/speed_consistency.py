"""Displayed velocity vs velocity implied by the trajectory coefficients (read-only).

    python analysis/sbj_location/speed_consistency.py <out json>

The 9 trajectory coefficients give release speed |v(y0)| in ft/s. A row whose displayed `velocity_kmh`
disagrees strongly with it carries a speed/type label from another pitch (lag) or a copied trajectory.
The offset between the two scales is estimated per season from the median, not assumed.
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
from visualbaseball.curated import load_rows

ROOT = Path(__file__).resolve().parents[2]
C = ["pitch_id", "velocity_kmh", "vx0", "vy0", "vz0", "trajectory_valid", "pitch_type_kr"]
KNOWN = {  # rows judged in the capture cases (results/case*_correspondence.csv)
    "20240504OBLG0-20240504OBLG0-073-04": "B: label from previous pitch (fastball trajectory, shown 123 fork)",
    "20240504OBLG0-20240504OBLG0-018-02": "B: label suspected from previous pitch",
    "20260509KTWO0-20260509KTWO0-093-04": "A/B: shown 135 slider, fastball-speed trajectory",
    "20210606HHNC0-20210606HHNC0-044-01": "E: shown 137 slider, real 145 fastball",
    "20210512SSKT0-20210512SSKT0-017-01": "E: shown 116 changeup, real 114 curve",
}
res = {"threshold_kmh": 8.0, "seasons": {}}
for s in range(2019, 2027):
    d = pd.DataFrame(load_rows(ROOT, "pitches", s, columns=C))
    d = d[d.trajectory_valid.fillna(False).astype(bool) & d.velocity_kmh.astype(float).gt(0)].copy()
    v = np.sqrt(d.vx0.astype(float)**2 + d.vy0.astype(float)**2 + d.vz0.astype(float)**2) * 1.09728  # ft/s -> km/h
    diff = d.velocity_kmh.astype(float) - v
    off = float(diff.median()); r = (diff - off).abs()
    e = {"rows": int(len(d)), "median_offset_kmh": round(off, 2), "p99_abs_residual": round(float(r.quantile(.99)), 2),
         "gt8": int((r > 8).sum()), "gt8_pct": round(100 * float((r > 8).mean()), 4)}
    k = d.assign(res=(diff - off).round(1))[d.pitch_id.isin(KNOWN)]
    if len(k): e["known_cases"] = {pid: {"residual_kmh": float(x), "note": KNOWN[pid]} for pid, x in zip(k.pitch_id, k.res)}
    res["seasons"][s] = e; print(s, json.dumps(e, ensure_ascii=False), flush=True)
Path(sys.argv[1]).write_text(json.dumps(res, ensure_ascii=False, indent=1))
