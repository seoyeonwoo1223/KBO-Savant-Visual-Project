"""Production eAA inference, withholding and rebuild contracts."""
import csv
import json
from pathlib import Path
import shutil

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler

from visualbaseball.estimated_arm_angle import HEIGHT_PATH, MODEL_PATH, _predict, season_estimates
from visualbaseball.metric_state import metric_input_hash

ROOT = Path(__file__).parents[1]


def inputs(root):
    model = root / MODEL_PATH
    model.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / MODEL_PATH, model)
    bio = root / 'data/curated/players/player_bio.parquet'
    bio.parent.mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist([{'player_id':'55146','player_name':'투수','throws':'R'}]),bio)
    path = root / HEIGHT_PATH
    path.parent.mkdir(parents=True)
    with path.open('w', newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['player_id','player_name','height_cm','source_url','source_sha256'])
        writer.writeheader()
        writer.writerow({'player_id':'55146','player_name':'투수','height_cm':185,'source_url':'https://www.koreabaseball.com/profile','source_sha256':'a'*64})
    return [{'season':2026,'pitcher_id':'55146','pitcher_name':'투수','trajectory_valid':True,'source_y0':50,
             'release_x_55':-65.,'release_z_55':180.,'vx_55':7.,'vy_55':-130.,'vz_55':-7.,'stadium':'잠실'} for _ in range(120)]


def test_frozen_inference_matches_sklearn_predict():
    model=json.loads((ROOT / MODEL_PATH).read_text())
    for name,x in [('bridge',np.array([1.85,.65,1.80,.05,.04])), ('angle',np.array([1.85,.93,.3,0.]))]:
        parameters=model[name]
        scaler=StandardScaler()
        scaler.mean_=np.array(parameters['standardization_mean'])
        scaler.scale_=np.array(parameters['standardization_scale'])
        scaler.n_features_in_=len(scaler.mean_)
        ridge=Ridge()
        ridge.coef_=np.array(parameters['ridge_coefficients'])
        ridge.intercept_=np.array(parameters['intercept'])
        steps=[scaler,ridge]
        if name=='angle': steps.insert(0,PolynomialFeatures(2,include_bias=False).fit(np.zeros((2,4))))
        expected=make_pipeline(*steps).predict(x.reshape(1,-1))[0]
        np.testing.assert_allclose(_predict(parameters,x),expected,atol=1e-12)


def test_single_season_value_ignores_pitch_display_type_and_flags_unseen_park(tmp_path):
    rows=inputs(tmp_path)
    result=season_estimates(tmp_path,2026,rows)['55146']
    assert result['status']=='estimated_KBO_angle_unvalidated'
    assert result['n']==120
    assert result['range']['status']=='reference_only_future_season_unvalidated'
    assert result['range']['low_deg'] < result['angle_deg'] < result['range']['high_deg']
    for i,r in enumerate(rows): r.update(pitch_type_code='FF' if i%2 else 'SL')
    assert season_estimates(tmp_path,2026,rows)['55146']==result
    rows[0]['stadium']='광주'
    unseen=season_estimates(tmp_path,2026,rows)['55146']
    assert unseen['angle_deg']==result['angle_deg']
    assert unseen['range']['status']=='unavailable_unseen_stadium_bias'
    assert unseen['range']['low_deg'] is None and unseen['range']['high_deg'] is None


def test_withholds_missing_height_small_samples_invalid_trajectory_and_extrapolation(tmp_path):
    rows=inputs(tmp_path)
    assert season_estimates(tmp_path,2026,rows[:99])['55146']['angle_deg'] is None
    invalid=[{**r,'trajectory_valid':False} for r in rows]
    assert season_estimates(tmp_path,2026,invalid)['55146']['n']==0
    for r in rows: r['release_z_55']=10.
    withheld=season_estimates(tmp_path,2026,rows)['55146']
    assert withheld['status'].startswith('withheld_') and withheld['angle_deg'] is None
    (tmp_path/HEIGHT_PATH).unlink()
    assert season_estimates(tmp_path,2026,rows)['55146']['status']=='withheld_missing_verified_height'


def test_invalid_identity_or_provenance_cannot_become_an_estimate(tmp_path):
    rows=inputs(tmp_path)
    path=tmp_path/HEIGHT_PATH
    path.write_text(path.read_text().replace('투수','다른선수'))
    result=season_estimates(tmp_path,2026,rows)['55146']
    assert result['status']=='withheld_height_identity_mismatch' and result['angle_deg'] is None
    path.write_text(path.read_text().replace('a'*64,'bad'))
    import pytest
    with pytest.raises(ValueError,match='provenance'): season_estimates(tmp_path,2026,rows)


def test_pitch_plot_rebuild_hash_tracks_height_and_frozen_model(tmp_path):
    inputs(tmp_path)
    baseline=metric_input_hash(tmp_path,2026,'pitch_arsenal')
    path=tmp_path/HEIGHT_PATH
    path.write_text(path.read_text().replace('185','186'))
    assert metric_input_hash(tmp_path,2026,'pitch_arsenal')!=baseline
    changed=metric_input_hash(tmp_path,2026,'pitch_arsenal')
    model=tmp_path/MODEL_PATH
    model.write_text(model.read_text()+'\n')
    assert metric_input_hash(tmp_path,2026,'pitch_arsenal')!=changed
