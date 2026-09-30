"""Are VB hMov/vMov (horizontal_movement_cm / vertical_movement_cm) derived from the 9 trajectory coefficients?"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
from visualbaseball.curated import load_rows
ROOT = Path(__file__).resolve().parents[2]
G = 32.174
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "analysis/sbj_location/results/movement_source.json"
C = ["x0","y0","z0","vx0","vy0","vz0","ax","ay","az","horizontal_movement_cm","vertical_movement_cm","trajectory_valid","arrival_time_s"]
def tpl(d, y):
    a = .5*d.ay; b = d.vy0; c = d.y0 - y; disc = (b*b - 4*a*c).clip(0)
    r1 = (-b - np.sqrt(disc))/(2*a); r2 = (-b + np.sqrt(disc))/(2*a)
    return np.where(np.abs(r1) < np.abs(r2), r1, r2)
res = {}
for s in (2019, 2023, 2024, 2025, 2026):
    d = pd.DataFrame(load_rows(ROOT, "pitches", s, columns=C)); d = d[d.trajectory_valid.fillna(False).astype(bool)]
    for c in C[:11]: d[c] = d[c].astype(float)
    d = d.dropna(subset=["horizontal_movement_cm","vertical_movement_cm"])
    best = []
    for start in (40.0, 50.0, 55.0, "y0"):
        for end, ye in (("front", 17/12), ("mid", 8.5/12), ("back", 0.0)):
            t = tpl(d, ye) - (0 if start == "y0" else tpl(d, start))
            hb = .5*d.ax*t*t*30.48; ivb = .5*(d.az + G)*t*t*30.48
            eh = np.abs(hb - d.horizontal_movement_cm); ev = np.abs(ivb - d.vertical_movement_cm)
            best.append({"start": start, "end": end, "hb_med_abs_cm": round(float(eh.median()),3), "hb_p99": round(float(eh.quantile(.99)),2),
                         "ivb_med_abs_cm": round(float(ev.median()),3), "ivb_p99": round(float(ev.quantile(.99)),2),
                         "hb_corr": round(float(np.corrcoef(hb, d.horizontal_movement_cm)[0,1]),5), "ivb_corr": round(float(np.corrcoef(ivb, d.vertical_movement_cm)[0,1]),5)})
    best.sort(key=lambda e: e["hb_med_abs_cm"] + e["ivb_med_abs_cm"])
    res[s] = {"n": int(len(d)), "best3": best[:3]}
    print(s, json.dumps(res[s], ensure_ascii=False), flush=True)
OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
