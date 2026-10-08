"""단위·물리적 대칭·결측·기준면 변환의 독립적인 기대값."""
import numpy as np
import pandas as pd
from features import derive, G, FT

def fixture(**changes):
    row = dict(x0=-2.,y0=55.,z0=6.,vx0=2.,vy0=-130.,vz0=0.,
               ax=0.,ay=0.,az=0.,pitcher_hand='Right',height_cm=190.,
               trajectory_valid=True,px=0.,pz=0.,horizontal_movement_cm=0.,vertical_movement_cm=0.)
    row.update(changes)
    return pd.DataFrame([row])

def test_straight_constant_speed_units():
    f,valid,_=derive(fixture())
    assert valid[0]
    dt=(55-17/12)/130
    np.testing.assert_allclose(f.tfront_s,dt,atol=1e-14)
    np.testing.assert_allclose(f.xfront_m,(-2+2*dt)*FT,atol=1e-14)
    np.testing.assert_allclose(f.speed55_mps,np.hypot(130,2)*FT,atol=1e-14)
    np.testing.assert_allclose(f.curvature55_per_m,0.,atol=1e-14)

def test_freefall_has_zero_induced_movement():
    f,_,_=derive(fixture(az=-G/FT))
    np.testing.assert_allclose(f.ivb50_cm,0.,atol=1e-12)
    assert f.movement_arm_axis50_deg.isna().all()
    dt=(55-17/12)/130
    np.testing.assert_allclose(f.zfront_m,6*FT-G*dt**2/2,atol=1e-12)

def test_left_right_mirror_preserves_arm_normalization():
    right,_,_=derive(fixture(ax=3.))
    left,_,_=derive(fixture(x0=2.,vx0=-2.,ax=-3.,pitcher_hand='Left'))
    for col in ['armside55_over_height','movement_arm_axis50_deg','armside_vx55_over_minus_vy']:
        np.testing.assert_allclose(right[col],left[col],atol=1e-12)

def test_equivalent_50ft_reference_preserves_trajectory():
    d=fixture(ax=3.,az=-20.)
    dt=5/130
    converted=d.copy()
    for pos,vel,acc in [('x0','vx0','ax'),('y0','vy0','ay'),('z0','vz0','az')]:
        converted[pos]=d[pos]+d[vel]*dt+.5*d[acc]*dt**2
        converted[vel]=d[vel]+d[acc]*dt
    a,_,_=derive(d);b,_,_=derive(converted)
    for col in ['x55_m','z55_m','vzfront_mps','ivb50_cm','dt_50_238_s']:
        np.testing.assert_allclose(a[col],b[col],atol=1e-12)

def test_missing_y0_unknown_reference_and_reverse_motion_fail_closed():
    for changes in [dict(y0=np.nan),dict(y0=54.),dict(vy0=130.),dict(ax=np.nan)]:
        f,valid,_=derive(fixture(**changes))
        assert not valid[0]
        assert f.isna().all().all()

def test_missing_bio_keeps_raw_kinematics_but_not_normalization():
    f,valid,_=derive(fixture(pitcher_hand=None,height_cm=np.nan))
    assert valid[0] and np.isfinite(f.speed55_mps.iloc[0])
    assert f.armside55_over_height.isna().all()

def test_curvature_matches_circular_instantaneous_formula():
    # At t=0 acceleration perpendicular to velocity gives kappa=|a|/|v|².
    f,_,_=derive(fixture(vx0=0.,ax=10.,ay=0.,az=0.))
    np.testing.assert_allclose(f.curvature55_per_m,10*FT/(130*FT)**2,atol=1e-14)
