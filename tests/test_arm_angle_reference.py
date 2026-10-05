"""Asymmetric scenarios preserve the point and handle boundaries/missingness."""
import numpy as np
import pytest
from visualbaseball.arm_angle_reference import reference_widths,reference_envelope


def spec():
    return {'asymmetric':{
        'down_scale':{'coefficients':[0.,0.],'intercept':3.,'minimum_scale_deg':1.},
        'up_scale':{'coefficients':[0.,4.],'intercept':4.,'minimum_scale_deg':1.},
        'down_multiplier':2.,'up_multiplier':2.}}


def test_directional_scales_and_envelope_use_scenarios_without_recentering():
    down,up=reference_widths(spec(),[40.,70.])
    np.testing.assert_allclose(down,[6.,6.]);np.testing.assert_allclose(up,[8.,16.])
    low,high=reference_envelope(spec(),[40.,70.])
    assert low==34. and high==86.
    assert reference_envelope(spec(),[70.])==(64.,86.)


def test_old_symmetric_reference_is_identical_and_angles_bound_display():
    old={'MLB_single_period_radius_deg':7.6}
    assert reference_envelope(old,[50.,55.])==(42.4,62.6)
    assert reference_envelope(spec(),[-89.,89.])==(-90.,90.)


def test_constant_directional_models_are_global_asymmetric_and_floor_is_positive():
    s=spec();s['asymmetric']['up_scale']['coefficients']=[0.,0.]
    assert reference_envelope(s,[50.])==(44.,58.)
    s['asymmetric']['up_scale']['intercept']=-2.
    assert reference_envelope(s,[50.])==(44.,52.)


def test_missing_or_invalid_reference_inputs_fail_closed():
    with pytest.raises(ValueError,match='Empty'):reference_envelope(spec(),[])
    with pytest.raises(ValueError,match='Nonfinite'):reference_envelope(spec(),[np.nan])
    s=spec();s['asymmetric']['up_multiplier']=-1.
    with pytest.raises(ValueError,match='multiplier'):reference_widths(s,[70.])
