"""Which y-plane of the raw trajectory reproduces the reported px / pz, per season (read-only)."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
from visualbaseball.curated import load_rows
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "analysis/sbj_location/results/report_planes.json"
COLS = ["pitch_id","x0","y0","z0","vx0","vy0","vz0","ax","ay","az","px","pz","sz_top","sz_bottom",
        "trajectory_valid","trajectory_status","arrival_time_s","plate_x_error_cm","plate_z_error_cm","source_y0"]
YS = np.round(np.arange(-1.0, 3.01, 1/24), 4)   # ft, 0.5-inch steps
def at(d, y):
    a = 0.5*d.ay; b = d.vy0; c = d.y0 - y
    disc = b*b - 4*a*c
    t = np.where(np.abs(a) > 1e-12, (-b - np.sqrt(disc.clip(0)))/(2*a), -c/b)
    t2 = np.where(np.abs(a) > 1e-12, (-b + np.sqrt(disc.clip(0)))/(2*a), t)
    t = np.where(np.abs(t) <= np.abs(t2), t, t2); t = np.where(disc < 0, np.nan, t)
    return d.x0 + d.vx0*t + .5*d.ax*t*t, d.z0 + d.vz0*t + .5*d.az*t*t
res = {}
for s in range(2019, 2027):
    d = pd.DataFrame(load_rows(ROOT, "pitches", s, columns=COLS))
    n = len(d); v = d[d.trajectory_valid.fillna(False).astype(bool)].copy()
    for c in COLS[1:14]: v[c] = v[c].astype(float)
    v = v.dropna(subset=["px","pz"])
    medx, medz = [], []
    for y in YS:
        x, z = at(v, y)
        medx.append(float(np.nanmedian(np.abs(x - v.px))*30.48)); medz.append(float(np.nanmedian(np.abs(z - v.pz))*30.48))
    ix, iz = int(np.argmin(medx)), int(np.argmin(medz))
    e = {"pitches": n, "trajectory_valid": int(len(v)), "status": d.trajectory_status.value_counts().head(6).to_dict(),
         "y0_values": d.source_y0.value_counts().head(4).to_dict(),
         "best_y_ft_for_px": float(YS[ix]), "median_abs_cm_at_best_px": round(medx[ix], 3),
         "best_y_ft_for_pz": float(YS[iz]), "median_abs_cm_at_best_pz": round(medz[iz], 3)}
    for name, y in (("front_17in", 17/12), ("mid_8.5in", 8.5/12), ("back_0", 0.0)):
        x, z = at(v, y); dx = np.abs(x - v.px)*30.48; dz = np.abs(z - v.pz)*30.48
        e[f"px_at_{name}"] = {"median_cm": round(float(np.nanmedian(dx)),3), "p99_cm": round(float(np.nanpercentile(dx,99)),2), "gt1cm_pct": round(100*float(np.nanmean(dx>1)),3)}
        e[f"pz_at_{name}"] = {"median_cm": round(float(np.nanmedian(dz)),3), "p99_cm": round(float(np.nanpercentile(dz,99)),2), "gt1cm_pct": round(100*float(np.nanmean(dz>1)),3)}
    # px at best plane, pz at best plane: disagreement share
    bx, _ = at(v, YS[ix]); _, bz = at(v, YS[iz])
    e["disagree_gt1cm_at_best"] = {"x_pct": round(100*float(np.nanmean(np.abs(bx-v.px)*30.48>1)),3), "z_pct": round(100*float(np.nanmean(np.abs(bz-v.pz)*30.48>1)),3)}
    res[s] = e; print(s, json.dumps(e, ensure_ascii=False), flush=True)
OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
