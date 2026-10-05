"""Numeric-model transport invariants and honest fallback/range contracts."""
import json
from pathlib import Path
import shutil
import warnings
import numpy as np
import pandas as pd

from visualbaseball.curated import normalize_trajectory
from visualbaseball.estimated_arm_angle import season_estimates
from visualbaseball.estimated_arm_angle_numeric import MODEL_PATH
from visualbaseball.numeric_arm_angle_features import pitch_features, plane_time, MODEL_FEATURES
from test_estimated_arm_angle import inputs

ROOT=Path(__file__).parents[1]


def test_missing_longitudinal_motion_has_no_finite_plane_crossing(tmp_path):
    data=numeric_rows(tmp_path)
    frame=pd.DataFrame(data[:1]).assign(height_cm=185.,pitcher_hand='Right',vy0=0.,ay=0.)
    with warnings.catch_warnings():
        warnings.simplefilter('error', RuntimeWarning)
        result=pitch_features(frame)
    assert np.isnan(plane_time(50.,0.,0.,55.))
    assert not result.numeric_valid.any()


def numeric_rows(root):
    inputs(root)
    shutil.copyfile(ROOT/MODEL_PATH,root/MODEL_PATH)
    # Widen fixture bounds to isolate range semantics from empirical support.
    path=root/MODEL_PATH;model=json.loads(path.read_text())
    model['training_feature_min']=[-100.]*len(MODEL_FEATURES)
    model['training_feature_max']=[100.]*len(MODEL_FEATURES)
    path.write_text(json.dumps(model))
    raw={'season':2026,'pitcher_id':'55146','pitcher_name':'투수','game_id':'20260701AB0','stadium':'잠실',
        'x0':-.65/.3048,'y0':50.,'z0':1.8/.3048,'vx0':6.,'vy0':-130.,'vz0':-5.,
        'ax':-8.,'ay':25.,'az':-10.,'sz_top':3.5,'sz_bottom':1.5,'pitch_type_code':'FF'}
    tf=float(plane_time(raw['y0'],raw['vy0'],raw['ay'],17/12))
    tm=float(plane_time(raw['y0'],raw['vy0'],raw['ay'],8.5/12))
    raw.update(px=raw['x0']+raw['vx0']*tm+.5*raw['ax']*tm*tm,
        pz=raw['z0']+raw['vz0']*tf+.5*raw['az']*tf*tf,
        horizontal_movement_cm=.5*raw['ax']*tf*tf*30.48,
        vertical_movement_cm=.5*(raw['az']+9.80665/.3048)*tf*tf*30.48)
    return [normalize_trajectory({**raw,'pitch_id':str(i)}) for i in range(240)]


def test_timestamp_reexpression_does_not_change_estimate_or_features(tmp_path):
    data=numeric_rows(tmp_path)
    before=season_estimates(tmp_path,2026,data)['55146']
    after_data=[]
    for raw in data:
        t=float(plane_time(raw['y0'],raw['vy0'],raw['ay'],55.))
        r={**raw,'y0':55.}
        for pos,vel,acc in [('x0','vx0','ax'),('z0','vz0','az')]:
            r[pos]=raw[pos]+raw[vel]*t+.5*raw[acc]*t*t
            r[vel]=raw[vel]+raw[acc]*t
        r['vy0']=raw['vy0']+raw['ay']*t
        after_data.append(normalize_trajectory(r))
    after=season_estimates(tmp_path,2026,after_data)['55146']
    assert before['model_id']=='eAA-v2'
    assert before['angle_deg']==after['angle_deg']
    assert before['range']==after['range']
    a=pd.DataFrame(data).assign(height_cm=185.,pitcher_hand='Right')
    b=pd.DataFrame(after_data).assign(height_cm=185.,pitcher_hand='Right')
    cols=[c.removeprefix('ff_') for c in MODEL_FEATURES]
    np.testing.assert_allclose(pitch_features(a)[cols],pitch_features(b)[cols],atol=1e-10)


def test_reference_envelope_and_single_angle_are_not_kbo_coverage(tmp_path):
    data=numeric_rows(tmp_path)
    for i,r in enumerate(data):
        if i>=120:r['game_id']='20260720AB0'
    result=season_estimates(tmp_path,2026,data)['55146']
    assert result['model_id']=='eAA-v2' and result['FF_pitches']==240
    assert result['KBO_coverage_validated'] is False
    assert result['range']['kind']=='model_reference_KBO_coverage_unknown'
    assert result['range']['low_deg']<result['angle_deg']<result['range']['high_deg']
    assert result['flags']['source_transition_span']
    assert set(result['numeric_sensitivity']['raw_source_period_deg'])=={'before0716','after0716'}
    assert 'pitch_types' not in result


def test_bad_trajectory_cannot_silently_fall_back_to_geometry(tmp_path):
    data=numeric_rows(tmp_path)
    for r in data:r['px']+=1.
    result=season_estimates(tmp_path,2026,data)['55146']
    assert result['status']=='withheld_numeric_quality' and result['angle_deg'] is None


def test_small_ff_falls_back_and_extrapolation_keeps_honest_range(tmp_path):
    data=numeric_rows(tmp_path)
    for r in data[80:]:r['pitch_type_code']='SL'
    result=season_estimates(tmp_path,2026,data)['55146']
    assert result['model_id']=='eAA-v1'
    assert result['numeric_fallback_reason']=='insufficient_valid_FF'
    data=[{**r,'pitch_type_code':'FF'} for r in data]
    path=tmp_path/MODEL_PATH;model=json.loads(path.read_text())
    model['training_feature_max'][0]=1.7
    path.write_text(json.dumps(model))
    result=season_estimates(tmp_path,2026,data)['55146']
    assert result['angle_deg'] is not None
    assert result['range']['low_deg'] is not None
    assert result['range']['status']=='reference_only_extrapolation_sensitivity_KBO_unvalidated'
    assert result['range']['extrapolation_error_bounded'] is False
    assert 'training_bounds_projection_deg' in result['numeric_sensitivity']


def test_numeric_model_file_changes_build_hash(tmp_path):
    from visualbaseball.metric_state import metric_input_hash
    numeric_rows(tmp_path)
    before=metric_input_hash(tmp_path,2026,'pitch_arsenal')
    path=tmp_path/MODEL_PATH;path.write_text(path.read_text()+'\n')
    assert metric_input_hash(tmp_path,2026,'pitch_arsenal')!=before
