"""Aggregation behavior under uneven exposure, contamination and invalid data."""
import numpy as np
import pandas as pd
import pytest
from visualbaseball.arm_angle_aggregation import aggregate_inputs,GEOMETRY,FASTBALL


def rows():
    values=np.r_[np.ones(100),np.full(10,11.)]
    d=pd.DataFrame({c:values.copy() for c in GEOMETRY+FASTBALL})
    d['pitcher_id']='a';d['game_id']=['one']*100+['two']*10
    d['pitch_type_code']='FF';d['numeric_valid']=True
    return d


def test_mean_matches_pitch_count_weights_and_caps_balance_games():
    d=rows()
    plain=aggregate_inputs(d,'mean').loc['a']
    cap=aggregate_inputs(d,'game_balanced_mean').loc['a']
    assert plain.height_m==pytest.approx(210/110)
    assert cap.height_m==pytest.approx((50+110)/60)
    assert cap.ff_speed55==pytest.approx((25+110)/35)
    assert cap.n==cap.n_ff==110


def test_median_trim_resist_contaminating_extreme_inputs():
    d=rows()
    for kind in ['median','trimmed10']:
        r=aggregate_inputs(d,kind).loc['a']
        assert r.height_m==r.ff_speed55==1.


def test_fastball_and_geometry_populations_remain_separate_and_invalid_excluded():
    d=rows();d.loc[:49,'pitch_type_code']='SL'
    d.loc[109,'numeric_valid']=False
    r=aggregate_inputs(d,'mean').loc['a']
    assert r.n==109 and r.n_ff==59
    assert r.height_m==pytest.approx(199/109)
    assert r.ff_speed55==pytest.approx(149/59)
    assert 'arm_angle' not in r


def test_unknown_method_and_missing_game_ids_fail_closed():
    d=rows()
    with pytest.raises(ValueError,match='Unknown'):aggregate_inputs(d,'other')
    with pytest.raises(ValueError,match='identified games'):aggregate_inputs(d.drop(columns='game_id'),'game_balanced_mean')


@pytest.mark.parametrize('method',['mean','median','trimmed10','game_balanced_mean'])
def test_empty_or_no_fastballs_preserve_missingness(method):
    d=rows();d['pitch_type_code']='SL'
    result=aggregate_inputs(d,method).loc['a']
    assert result.n_ff==0 and np.isnan(result.ff_speed55)
    assert aggregate_inputs(d.iloc[:0],method).empty
