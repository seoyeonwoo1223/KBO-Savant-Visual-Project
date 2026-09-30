"""Park/day and plate-location correction for Visual Baseball HB/IVB (Pitch Arsenal).

Validated against pitch-matched TrackMan data for 2019-2024 in
analysis/movement_calibration/ (method `fe_day_loc_robust_shrink`). It needs no
TrackMan data at run time:

1. Remove the plate-location component: VB reads less movement in the direction the
   pitch ended up. The coefficients are the six-season TrackMan averages.
2. Fit movement = pitcher x pitch type + stadium x game day by alternating means.
3. Refit without pitches whose residual exceeds OUTLIER_SD robust SDs.
4. Shrink each stadium-day effect toward its stadium's season effect by n/(n+SHRINK_PITCHES).

The corrected value keeps the VB scale; stadium-day effects are centred on the pitch-weighted
season mean, so the correction moves stadiums relative to each other, not the league level.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# cm of VB-minus-TrackMan movement per ft of plate location: (px, pz - zone centre).
LOCATION_COEFFICIENTS = {"hb": (-0.5638, -0.0675), "ivb": (0.4665, -1.0485)}
SHRINK_PITCHES = 300
OUTLIER_SD = 4.0
ITERATIONS = 30
COLUMNS = {"hb": "horizontal_movement_cm", "ivb": "vertical_movement_cm"}


def _float(values) -> np.ndarray:
    return pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(float)


def _stadium_day_effects(frame: pd.DataFrame, value: pd.Series) -> pd.Series:
    """Return shrunk stadium-day effects keyed by 'stadium|day', centred on fitted pitches."""
    key, group = frame["key"], frame["group"]
    keep = pd.Series(True, index=frame.index)
    for attempt in range(2):
        y, k, g = value[keep], key[keep], group[keep]
        delta = pd.Series(0.0, index=y.index)
        for _ in range(ITERATIONS):
            theta = (y - delta).groupby(g).transform("mean")
            delta = (y - theta).groupby(k).transform("mean")
        if attempt == 0:
            full = value - group.map(theta.groupby(g).first()) - key.map(delta.groupby(k).first())
            scale = 1.4826 * (full - full.median()).abs().median()
            keep = (full.abs() <= OUTLIER_SD * scale).fillna(False) if scale > 0 else keep
    per_key = delta.groupby(k).first()
    stadium_of = pd.Series([name.split("|", 1)[0] for name in per_key.index], index=per_key.index)
    season = (y - theta).groupby(frame.loc[y.index, "stadium"]).mean()
    count = k.value_counts().reindex(per_key.index)
    shrunk = stadium_of.map(season) + count / (count + SHRINK_PITCHES) * (per_key - stadium_of.map(season))
    return shrunk - key.map(shrunk).fillna(0.0).mean()


def calibrate(rows: list[dict], codes: list[str]) -> list[tuple[float | None, float | None]]:
    """Corrected (HB cm, IVB cm) for each row; None where VB gave no movement."""
    frame = pd.DataFrame({
        "pitcher": [str(r.get("pitcher_id") or "") for r in rows], "code": codes,
        "stadium": [str(r.get("stadium") or "") for r in rows],
        "day": [str(r.get("game_id") or "")[:8] for r in rows],
        "hb": _float([r.get(COLUMNS["hb"]) for r in rows]), "ivb": _float([r.get(COLUMNS["ivb"]) for r in rows]),
        "px": _float([r.get("px") for r in rows]), "pz": _float([r.get("pz") for r in rows]),
        "sz_top": _float([r.get("sz_top") for r in rows]), "sz_bottom": _float([r.get("sz_bottom") for r in rows]),
    })
    frame["key"] = frame["stadium"] + "|" + frame["day"]
    frame["group"] = frame["pitcher"] + "|" + frame["code"]
    centre = (frame["sz_top"] + frame["sz_bottom"]) / 2
    centre = centre.fillna(centre.median())
    frame["z"] = frame["pz"] - centre
    fit = frame["hb"].notna() & frame["ivb"].notna() & frame["px"].notna() & frame["pz"].notna() & (frame["code"] != "") & (frame["pitcher"] != "")
    corrected = {}
    for name, (kx, kz) in LOCATION_COEFFICIENTS.items():
        # Pitches without a plate location keep their movement but get no location term.
        location = (kx * frame["px"] + kz * frame["z"]).fillna(0.0)
        value = frame[name] - location
        effects = _stadium_day_effects(frame[fit], value[fit]) if fit.any() else pd.Series(dtype=float)
        corrected[name] = (value - frame["key"].map(effects).fillna(0.0)).to_numpy()
    return [(None if np.isnan(hb) else float(hb), None if np.isnan(ivb) else float(ivb))
            for hb, ivb in zip(corrected["hb"], corrected["ivb"])]
