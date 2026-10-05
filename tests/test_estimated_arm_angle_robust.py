"""Public v3 inference, frozen polynomial transport and reference contracts."""
import json
from pathlib import Path
import numpy as np
from test_estimated_arm_angle_numeric import numeric_rows
from visualbaseball.curated import normalize_trajectory
from visualbaseball.estimated_arm_angle import season_estimates
from visualbaseball.estimated_arm_angle_numeric import ROBUST_MODEL_PATH
from visualbaseball.numeric_arm_angle_features import plane_time,MODEL_FEATURES

ROOT=Path(__file__).parents[1]


def robust_rows(root):
    rows=numeric_rows(root)
    candidate=ROOT/'data/models/estimated_arm_angle_v3.json'
    model=json.loads(candidate.read_text())
    model['training_feature_min']=[-100.]*len(MODEL_FEATURES)
    model['training_feature_max']=[100.]*len(MODEL_FEATURES)
    (root/ROBUST_MODEL_PATH).write_text(json.dumps(model))
    return rows


def test_public_v3_prefers_robust_model_and_keeps_single_point_not_interval_midpoint(tmp_path):
    rows=robust_rows(tmp_path)
    result=season_estimates(tmp_path,2026,rows)['55146']
    assert result['model_id']=='eAA-v3'
    assert result['aggregation']=='trimmed10'
    assert result['range']['shape']=='global_asymmetric_reference'
    r=result['range'];point=result['angle_deg']
    assert r['low_deg']<point<r['high_deg']
    assert abs(point-(r['low_deg']+r['high_deg'])/2)>.01
    assert r['MLB_reference_down_deg']!=r['MLB_reference_up_deg']
    assert result['KBO_coverage_validated'] is False
    assert r['conditional_subgroup_coverage_guaranteed'] is False


def test_polynomial_robust_model_is_invariant_to_50_55ft_reexpression(tmp_path):
    rows=robust_rows(tmp_path)
    before=season_estimates(tmp_path,2026,rows)['55146']
    converted=[]
    for raw in rows:
        t=float(plane_time(raw['y0'],raw['vy0'],raw['ay'],55.))
        r={**raw,'y0':55.,'vy0':raw['vy0']+raw['ay']*t}
        for pos,vel,acc in [('x0','vx0','ax'),('z0','vz0','az')]:
            r[pos]=raw[pos]+raw[vel]*t+.5*raw[acc]*t*t
            r[vel]=raw[vel]+raw[acc]*t
        converted.append(normalize_trajectory(r))
    after=season_estimates(tmp_path,2026,converted)['55146']
    assert after['angle_deg']==before['angle_deg']
    assert after['range']==before['range']


def test_unusable_numeric_inputs_do_not_get_robust_point(tmp_path):
    rows=robust_rows(tmp_path)
    for r in rows:r['px']+=1.
    result=season_estimates(tmp_path,2026,rows)['55146']
    assert result['model_id']=='eAA-v3' and result['angle_deg'] is None
    assert result['status']=='withheld_numeric_quality'


def test_small_fastball_sample_uses_frozen_v1(tmp_path):
    rows=robust_rows(tmp_path)
    for r in rows[80:]:r['pitch_type_code']='SL'
    result=season_estimates(tmp_path,2026,rows)['55146']
    assert result['model_id']=='eAA-v1'
    assert result['numeric_fallback_reason']=='insufficient_valid_FF'


def test_robust_model_change_invalidates_build_state(tmp_path):
    from visualbaseball.metric_state import metric_input_hash
    robust_rows(tmp_path)
    before=metric_input_hash(tmp_path,2026,'pitch_arsenal')
    path=tmp_path/ROBUST_MODEL_PATH;path.write_text(path.read_text()+'\n')
    assert metric_input_hash(tmp_path,2026,'pitch_arsenal')!=before
