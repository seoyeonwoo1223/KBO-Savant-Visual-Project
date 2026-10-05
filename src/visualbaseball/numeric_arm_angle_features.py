"""Shared, vectorized numerical eAA features in declared 50/55ft frames."""
from __future__ import annotations
import numpy as np
import pandas as pd

FT_M = .3048
G = 9.80665
GEOMETRY = ['height_m', 'left_hand', 'z55_over_height', 'side55_over_height']
KINEMATICS = ['speed55', 'armside_vx_over_minus_vy', 'vz_over_minus_vy', 'flight55_to_plate']
MOVEMENT = ['movement_axis_arm_sin', 'movement_axis_up_cos', 'movement_size_m']
MODEL_FEATURES = GEOMETRY+['ff_'+c for c in KINEMATICS+MOVEMENT]


def plane_time(y, vy, ay, target):
    y, vy, ay = [np.asarray(x, float) for x in (y, vy, ay)]
    with np.errstate(invalid='ignore', divide='ignore'):
        disc = vy*vy-2*ay*(y-target)
        r1 = (-vy+np.sqrt(disc))/ay; r2 = (-vy-np.sqrt(disc))/ay
        t = np.where(abs(r1) < abs(r2), r1, r2)
        t = np.where(abs(ay) < 1e-12, (target-y)/vy, t)
        # No finite crossing for stationary/missing longitudinal motion.
        return np.where(np.isfinite(t), t, np.nan)


def pitch_features(frame: pd.DataFrame, movement=None):
    d = frame.copy()
    p = d[['x0','y0','z0']].to_numpy(float)*FT_M
    v = d[['vx0','vy0','vz0']].to_numpy(float)*FT_M
    a = d[['ax','ay','az']].to_numpy(float)*FT_M
    hand = d.pitcher_hand.map({'Right':1.,'Left':-1.}).to_numpy()
    h = d.height_cm.to_numpy(float)/100
    t55 = plane_time(p[:,1],v[:,1],a[:,1],55*FT_M)
    t50 = plane_time(p[:,1],v[:,1],a[:,1],50*FT_M)
    end = plane_time(p[:,1],v[:,1],a[:,1],17/12*FT_M)
    p55 = p+v*t55[:,None]+.5*a*t55[:,None]**2
    v55 = v+a*t55[:,None]
    if movement is None:
        hb = .5*a[:,0]*(end-t50)**2
        ivb = .5*(a[:,2]+G)*(end-t50)**2
    else:
        hb, ivb = np.asarray(movement,float).T/100
    size = np.hypot(hb,ivb)
    with np.errstate(invalid='ignore', divide='ignore'):
        d['height_m'] = h; d['left_hand'] = (hand < 0).astype(float)
        d['z55_over_height'] = p55[:,2]/h
        d['side55_over_height'] = -hand*p55[:,0]/h
        d['speed55'] = np.linalg.norm(v55,axis=1)
        d['armside_vx_over_minus_vy'] = hand*v55[:,0]/(-v55[:,1])
        d['vz_over_minus_vy'] = v55[:,2]/(-v55[:,1])
        d['flight55_to_plate'] = end-t55
        d['movement_axis_arm_sin'] = -hand*hb/size
        d['movement_axis_up_cos'] = ivb/size
        d['movement_size_m'] = size
    valid = (np.isfinite(d[GEOMETRY+KINEMATICS+MOVEMENT]).all(axis=1) & d.height_cm.between(140,220)
        & d.y0.isin([50.,55.]) & d.pitcher_hand.isin(['Right','Left']) & (v55[:,1] < 0)
        & (abs(p55[:,0]) <= 2) & (p55[:,2] >= .05) & (p55[:,2] <= 2.7)
        & d.speed55.between(15,55) & d.flight55_to_plate.between(.2,.8) & (abs(t55) < .15))
    if 'trajectory_valid' in d:
        valid &= d.trajectory_valid.fillna(False)
    d['numeric_valid'] = valid
    return d


def quality_mask(d):
    """KBO report/trajectory checks at its actual ABS coordinate planes."""
    y,vy,ay = [d[c].to_numpy(float) for c in ['y0','vy0','ay']]
    front = plane_time(y,vy,ay,17/12)
    mid = plane_time(y,vy,ay,8.5/12)
    t50 = plane_time(y,vy,ay,50.)
    xplane = np.where(d.season.to_numpy() >= 2024,mid,front)
    x = (d.x0+d.vx0*xplane+.5*d.ax*xplane*xplane-d.px)*FT_M*100
    z = (d.z0+d.vz0*front+.5*d.az*front*front-d.pz)*FT_M*100
    hb = d.horizontal_movement_cm-.5*d.ax*(front-t50)**2*FT_M*100
    ivb = d.vertical_movement_cm-.5*(d.az+G/FT_M)*(front-t50)**2*FT_M*100
    residual = np.column_stack([x,z,hb,ivb])
    return (np.isfinite(residual).all(axis=1) & (abs(residual) <= 1.).all(axis=1)
        & d.ay.between(5,55) & np.hypot(d.ax,d.az+G/FT_M).le(45.)).to_numpy()


def season_features(d, aggregation='mean'):
    if aggregation != 'mean':
        from .arm_angle_aggregation import aggregate_inputs
        return aggregate_inputs(d,aggregation)
    q = d.loc[d.numeric_valid]
    g = q.groupby('pitcher_id')
    out = g[GEOMETRY].mean()
    out['n'] = g.size()
    ff = q.loc[q.pitch_type_code.eq('FF')].groupby('pitcher_id')
    for c in KINEMATICS+MOVEMENT:
        out['ff_'+c] = ff[c].mean()
    out['n_ff'] = ff.size().reindex(out.index).fillna(0).astype(int)
    return out
