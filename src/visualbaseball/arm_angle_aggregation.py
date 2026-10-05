"""Common MLB/KBO feature aggregation; never aggregates arm-angle labels."""
from __future__ import annotations
import numpy as np
import pandas as pd

METHODS = ('mean', 'median', 'trimmed10', 'game_balanced_mean')
GEOMETRY = ['height_m','left_hand','z55_over_height','side55_over_height']
FASTBALL = ['speed55','armside_vx_over_minus_vy','vz_over_minus_vy','flight55_to_plate',
            'movement_axis_arm_sin','movement_axis_up_cos','movement_size_m']


def trimmed_mean(values):
    values=np.sort(np.asarray(values,float))
    cut=int(len(values)*.1)
    return float(values[cut:len(values)-cut].mean()) if len(values) else np.nan


def _aggregate(q, columns, method, game_cap):
    group=q.groupby('pitcher_id')
    if method=='mean':return group[columns].mean()
    if method=='median':return group[columns].median()
    if method=='trimmed10':return group[columns].agg(trimmed_mean)
    if 'game_id' not in q or q.game_id.isna().any() or q.game_id.astype(str).eq('').any():
        raise ValueError('Game-balanced eAA requires identified games')
    size=q.groupby(['pitcher_id','game_id']).pitcher_id.transform('size')
    weight=np.minimum(1.,game_cap/size)
    denom=weight.groupby(q.pitcher_id).sum()
    return q[columns].mul(weight,axis=0).groupby(q.pitcher_id).sum().div(denom,axis=0)


def aggregate_inputs(frame, method='mean'):
    """Per-pitch mean, marginal median/trim, or capped-game pitch weights.

    Game caps are 50 all-pitches / 25 fastballs; they balance exposure and are
    not estimated measurement precision. Counts always describe valid inputs.
    """
    if method not in METHODS:raise ValueError(f'Unknown eAA aggregation: {method}')
    q=frame.loc[frame.numeric_valid]
    out=_aggregate(q,GEOMETRY,method,50.)
    out['n']=q.groupby('pitcher_id').size()
    ff=q.loc[q.pitch_type_code.eq('FF')]
    fb=_aggregate(ff,FASTBALL,method,25.)
    out=out.join(fb.rename(columns={c:'ff_'+c for c in FASTBALL}))
    out['n_ff']=ff.groupby('pitcher_id').size().reindex(out.index).fillna(0).astype(int)
    return out
