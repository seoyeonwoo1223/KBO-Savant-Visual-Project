"""Relative movement correction for numerical eAA inputs.

At the documented 2026 source transition, shrink daily park effects toward
their park/source-period mean. This keeps the season-wide VB level and does
not change canonical trajectories, Pitch Plot movement, or an SSG scale.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from .movement_calibration import LOCATION_COEFFICIENTS, SHRINK_PITCHES, OUTLIER_SD, ITERATIONS


def source_epoch(season: int, game_id: str) -> str:
    if season != 2026:
        return 'single'
    return 'after0716' if str(game_id)[:8] >= '20260716' else 'before0716'


def _period_day_effects(frame, value):
    key, group = frame['key'], frame['group']
    keep = pd.Series(True, index=frame.index)
    for attempt in range(2):
        y, k, g = value[keep], key[keep], group[keep]
        delta = pd.Series(0., index=y.index)
        for _ in range(ITERATIONS):
            theta = (y-delta).groupby(g).transform('mean')
            delta = (y-theta).groupby(k).transform('mean')
        if attempt == 0:
            residual = value-group.map(theta.groupby(g).first())-key.map(delta.groupby(k).first())
            scale = 1.4826*(residual-residual.median()).abs().median()
            if scale > 0:
                keep = residual.abs().le(OUTLIER_SD*scale).fillna(False)
    per_key = delta.groupby(k).first()
    pool_of_key = frame.groupby('key')['pool'].first().reindex(per_key.index)
    period = (y-theta).groupby(frame.loc[y.index, 'pool']).mean()
    count = k.value_counts().reindex(per_key.index)
    centre = pool_of_key.map(period)
    shrunk = centre+count/(count+SHRINK_PITCHES)*(per_key-centre)
    return shrunk-key.map(shrunk).fillna(0.).mean()


def calibrate_eaa(rows: list[dict], codes: list[str], season: int):
    if len(rows) != len(codes):
        raise ValueError('Movement rows/codes length mismatch')
    if not rows:
        return []
    frame = pd.DataFrame({
        'pitcher': [str(r.get('pitcher_id') or '') for r in rows], 'code': codes,
        'stadium': [str(r.get('stadium') or '') for r in rows],
        'day': [str(r.get('game_id') or '')[:8] for r in rows],
        'epoch': [source_epoch(season, r.get('game_id', '')) for r in rows]})
    for name, key in [('hb','horizontal_movement_cm'), ('ivb','vertical_movement_cm'),
        ('px','px'), ('pz','pz'), ('top','sz_top'), ('bottom','sz_bottom')]:
        frame[name] = pd.to_numeric(pd.Series([r.get(key) for r in rows]), errors='coerce')
    frame['key'] = frame.stadium+'|'+frame.day
    frame['group'] = frame.pitcher+'|'+frame.code
    frame['pool'] = frame.stadium+'|'+frame.epoch
    centre = (frame.top+frame.bottom)/2
    frame['z'] = frame.pz-centre.fillna(centre.median())
    valid = frame[['hb','ivb','px','pz']].notna().all(axis=1) & frame.code.ne('') & frame.pitcher.ne('')
    outputs = []
    for name, (kx, kz) in LOCATION_COEFFICIENTS.items():
        value = frame[name]-(kx*frame.px+kz*frame.z).fillna(0.)
        effect = _period_day_effects(frame.loc[valid], value.loc[valid]) if valid.any() else pd.Series(dtype=float)
        outputs.append((value-frame.key.map(effect).fillna(0.)).to_numpy())
    return [(float(a) if np.isfinite(a) else None, float(b) if np.isfinite(b) else None)
        for a, b in zip(*outputs)]
