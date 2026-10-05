"""Frozen numerical eAA estimates and model-reference sensitivity envelopes.

These are single pitcher-period estimates. Bounds are MLB model-error and
numeric-source sensitivity references; KBO coverage is unknown.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .estimated_arm_angle import _heights, _name, _predict
from .numeric_arm_angle_features import MODEL_FEATURES, pitch_features, quality_mask, season_features
from .eaa_movement_calibration import calibrate_eaa, source_epoch
from .movement_calibration import calibrate
from .arm_angle_reference import reference_widths, reference_envelope

MODEL_PATH = 'data/models/estimated_arm_angle_v2.json'
ROBUST_MODEL_PATH = 'data/models/estimated_arm_angle_v3.json'


def season_estimates_numeric(root: Path, season: int, rows: list[dict], fallback: dict, model_path=None) -> dict:
    path=Path(model_path) if model_path is not None else root/(ROBUST_MODEL_PATH if (root/ROBUST_MODEL_PATH).exists() else MODEL_PATH)
    model = json.loads(path.read_text())
    model_id=model.get('model_id')
    aggregation=model.get('aggregation','mean')
    if model_id not in {'eAA-v2','eAA-v3'} or model.get('features') != MODEL_FEATURES or model.get('schema_version') != 1:
        raise ValueError('Unsupported numerical eAA model')
    selected = [r for r in rows if r.get('season') == season and r.get('pitcher_id')]
    if not selected:
        return fallback
    heights = _heights(root)
    bio_path = root/'data/curated/players/player_bio.parquet'
    if not bio_path.exists():
        return fallback
    bio = {str(x['player_id']):x for x in pq.read_table(bio_path,columns=['player_id','player_name','throws']).to_pylist()}
    d = pd.DataFrame(selected)
    d['pitcher_id'] = d.pitcher_id.astype(str)
    required = ['x0','y0','z0','vx0','vy0','vz0','ax','ay','az','px','pz','sz_top','sz_bottom',
        'horizontal_movement_cm','vertical_movement_cm','pitch_type_code','stadium','game_id','trajectory_valid']
    if any(c not in d for c in required):
        return fallback
    d['height_cm'] = d.pitcher_id.map(lambda p: heights.get(p,{}).get('height_cm'))
    d['height_cm'] = pd.to_numeric(d.height_cm,errors='coerce')
    d['pitcher_hand'] = d.pitcher_id.map(lambda p:{'R':'Right','L':'Left'}.get(bio.get(p,{}).get('throws')))
    names = d.pitcher_name.map(_name)
    height_names = d.pitcher_id.map(lambda p:_name(heights.get(p,{}).get('player_name')))
    bio_names = d.pitcher_id.map(lambda p:_name(bio.get(p,{}).get('player_name')))
    identities = (names.eq(height_names) & names.eq(bio_names)).to_numpy()
    numeric_columns = ['x0','y0','z0','vx0','vy0','vz0','ax','ay','az','px','pz','sz_top','sz_bottom',
        'horizontal_movement_cm','vertical_movement_cm']
    d[numeric_columns] = d[numeric_columns].apply(pd.to_numeric,errors='coerce')
    qualified = quality_mask(d) & identities
    if not np.isfinite(d[numeric_columns].to_numpy(float)).any():
        return fallback
    codes = d.pitch_type_code.fillna('').tolist()
    epoch_corrected = calibrate_eaa(selected,codes,season)
    legacy_corrected = calibrate(selected,codes)
    variants = {}
    for label, movement in [('raw',None),('relative',legacy_corrected),('epoch',epoch_corrected)]:
        part = pitch_features(d,movement)
        part['numeric_valid'] &= qualified
        variants[label] = (part,season_features(part,aggregation))
    total = d.groupby('pitcher_id').size()
    predictions = {}
    for label, (_,features) in variants.items():
        complete = np.isfinite(features[MODEL_FEATURES]).all(axis=1)
        predictions[label] = {pid:float(_predict(model['angle'],row[MODEL_FEATURES].to_numpy(float)))
            for pid,row in features.loc[complete].iterrows()}
    result = dict(fallback)
    valid_counts = variants['epoch'][1]['n'].to_dict()
    for pid, payload in fallback.items():
        if payload.get('angle_deg') is not None and valid_counts.get(pid,0) < model['minimum_pitches']:
            result[pid] = {**payload, 'angle_deg':None, 'model_id':model_id,
                'status':'withheld_numeric_quality', 'n':int(valid_counts.get(pid,0)),
                'range':{'kind':'model_reference_KBO_coverage_unknown','status':'withheld_estimate',
                    'low_deg':None,'high_deg':None}}
    epochs_full = d.game_id.map(lambda x:source_epoch(season,x))
    period_features = {epoch:season_features(variants['raw'][0].loc[epochs_full.eq(epoch)],aggregation)
        for epoch in epochs_full.unique()} if epochs_full.nunique() > 1 else {}
    for pid,row in variants['epoch'][1].iterrows():
        if row.n < model['minimum_pitches'] or row.n_ff < model['minimum_FF_pitches']:
            if pid in result:
                result[pid] = {**result[pid], 'numeric_fallback_reason':'insufficient_valid_FF',
                    'numeric_FF_pitches':int(row.n_ff)}
            continue
        point = predictions['epoch'].get(pid)
        if point is None or not np.isfinite(point) or abs(point) > 90:
            if pid in result:
                result[pid] = {**result[pid], 'angle_deg':None, 'model_id':model_id,
                    'status':'withheld_invalid_prediction', 'range':{'status':'withheld_estimate',
                        'kind':'model_reference_KBO_coverage_unknown','low_deg':None,'high_deg':None}}
            continue
        values = [predictions[k][pid] for k in predictions if pid in predictions[k]]
        player = d.loc[d.pitcher_id.eq(pid)]
        epochs = sorted(set(source_epoch(season,x) for x in player.game_id))
        # Retain both observed source-period estimates as sensitivity anchors.
        # Their spread is not an estimated true change or a confidence bound.
        period_values = {}
        if len(epochs) > 1:
            for epoch in epochs:
                small = period_features[epoch]
                if pid in small.index and small.loc[pid,'n_ff'] >= model['minimum_FF_pitches']:
                    features = small.loc[pid,MODEL_FEATURES].to_numpy(float)
                    if np.isfinite(features).all():
                        period_values[epoch] = float(_predict(model['angle'],features))
            values += list(period_values.values())
        x = row[MODEL_FEATURES].to_numpy(float)
        outside = [c for i,c in enumerate(MODEL_FEATURES) if x[i] < model['training_feature_min'][i]
            or x[i] > model['training_feature_max'][i]]
        clipped = np.clip(x,model['training_feature_min'],model['training_feature_max'])
        clipped_point = float(_predict(model['angle'],clipped))
        if outside:
            values.append(clipped_point)
        parks = set(player.stadium.fillna(''))
        unknown = parks-set(model['paired_TM_stadiums'])
        low,high=reference_envelope(model['range'],values)
        down,up=reference_widths(model['range'],[point])
        asymmetric=model['range'].get('asymmetric')
        result[pid] = {'model_id':model_id,'scope':'pitcher_season','angle_deg':round(point,4),
            'status':'estimated_KBO_angle_unvalidated','n':int(row.n),'total_pitches':int(total[pid]),
            'height_cm':float(heights[pid]['height_cm']),'FF_pitches':int(row.n_ff),
            'range':{'kind':'model_reference_KBO_coverage_unknown',
                'status':'reference_only_extrapolation_sensitivity_KBO_unvalidated' if outside else 'reference_only_numeric_sensitivity_KBO_unvalidated',
                'low_deg':round(low,4),
                'high_deg':round(high,4),
                'extrapolation_error_bounded':False if outside else None},
            'flags':{'source_transition_span':len(epochs)>1,'future_season':season>2024,
                'outside_MLB_training_features':outside,'unpaired_TM_stadiums':sorted(unknown),
                'trajectory_quality_exclusions':int(total[pid]-row.n)},
            'numeric_sensitivity':{'raw_deg':round(predictions['raw'].get(pid,point),4),
                'relative_adjusted_deg':round(predictions['relative'].get(pid,point),4),
                'epoch_adjusted_deg':round(point,4),
                'training_bounds_projection_deg':round(clipped_point,4),
                'raw_source_period_deg':{k:round(v,4) for k,v in period_values.items()}},
            'method':'common_55ft_geometry_kinematics_50ft_movement; source-period relative adjustment',
            'KBO_coverage_validated':False}
        if asymmetric:
            result[pid]['aggregation']=aggregation
            result[pid]['range'].update({'shape':asymmetric['adaptation']+'_reference',
                'MLB_reference_down_deg':round(float(down[0]),4),'MLB_reference_up_deg':round(float(up[0]),4),
                'conditional_subgroup_coverage_guaranteed':False})
            result[pid]['flags'].update({'high_angle_calibration_sparse':bool(point>=55 and asymmetric['calibration_predicted55_players']<30),
                'outside_interval_training_predictions':bool(min(values)<asymmetric['training_OOF_prediction_min'] or max(values)>asymmetric['training_OOF_prediction_max'])})
        else:
            result[pid]['range']['MLB_reference_radius_deg']=round(float(down[0]),4)
    return result
