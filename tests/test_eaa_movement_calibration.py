import numpy as np
import pytest

from visualbaseball.eaa_movement_calibration import calibrate_eaa
from visualbaseball.movement_calibration import calibrate


def rows(season):
    # All players visit both parks in both source periods. Inject opposite
    # source shifts; player movement stays fixed. Tiny noise avoids MAD=0.
    result = []
    for day in [f'{season}0702', f'{season}0705', f'{season}0720', f'{season}0724']:
        sign = 1 if day[-4:] < '0716' else -1
        for park, park_sign in [('수원',1), ('문학',-1)]:
            for pid in range(4):
                for pitch in range(8):
                    result.append({'pitcher_id':str(pid), 'game_id':day+'A', 'stadium':park,
                        'horizontal_movement_cm': -15+pid+park_sign*sign*12+(pitch-3.5)*.03,
                        'vertical_movement_cm':45+pid+park_sign*sign*5+(pitch-3.5)*.02,
                        'px':0.,'pz':2.5,'sz_top':3.5,'sz_bottom':1.5})
    return result


def test_same_algorithm_without_source_transition():
    data=rows(2025); codes=['FF']*len(data)
    np.testing.assert_allclose(calibrate_eaa(data,codes,2025),calibrate(data,codes),atol=1e-12)


def test_period_shrinkage_recovers_injected_relative_bias():
    data=rows(2026); codes=['FF']*len(data)
    old=np.asarray(calibrate(data,codes)); new=np.asarray(calibrate_eaa(data,codes,2026))
    truth=np.asarray([[-15+int(r['pitcher_id']),45+int(r['pitcher_id'])] for r in data])
    assert np.mean(abs(new-truth)) < .2
    assert np.mean(abs(old-truth)) > 5
    # Balanced zero-sum injected shifts preserve the observed season level.
    np.testing.assert_allclose(new.mean(axis=0),truth.mean(axis=0),atol=.02)


def test_missing_measurement_is_preserved_and_empty_input():
    data=rows(2026);data[0]['horizontal_movement_cm']=None
    got=calibrate_eaa(data,['FF']*len(data),2026)
    assert got[0][0] is None
    assert calibrate_eaa([],[],2026)==[]
    with pytest.raises(ValueError):calibrate_eaa(data,[],2026)
