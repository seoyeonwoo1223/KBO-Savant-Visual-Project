import math

import numpy as np
import pandas as pd
import pytest

from visualbaseball import abs_explorer as ax
from visualbaseball import abs_run_value as arv
from visualbaseball import abs_zone as az
from visualbaseball.curated import _at_plane

TRAJECTORY = {"x0": -2.1, "y0": 50.0, "z0": 5.8, "vx0": 6.5, "vy0": -134.0, "vz0": -4.2, "ax": -9.0, "ay": 28.0, "az": -20.0}


def _plane(row, y):
    return az.plane_position_cm(*(np.array([row[k]]) for k in ("x0", "y0", "z0", "vx0", "vy0", "vz0", "ax", "ay", "az")), y)


def test_plane_position_matches_curated_helper_on_every_plane():
    for y in (az.FRONT_PLANE_Y_FT, az.MID_PLANE_Y_FT, az.BACK_PLANE_Y_FT, 50.0):
        x, z = _plane(TRAJECTORY, y)
        expected = _at_plane(TRAJECTORY, y)
        assert x[0] == pytest.approx(expected[0], abs=1e-9)
        assert z[0] == pytest.approx(expected[1], abs=1e-9)


def test_plane_position_is_nan_without_a_trajectory():
    row = dict(TRAJECTORY, ay=None)
    x, z = az.plane_position_cm(*([row[k]] for k in ("x0", "y0", "z0", "vx0", "vy0", "vz0", "ax", "ay", "az")), 0.0)
    assert np.isnan(x[0]) and np.isnan(z[0])


def test_rules_follow_the_official_shares_and_the_2025_downward_shift():
    top24, bottom24 = az.zone_bounds_cm(180.0, 2024)
    top25, bottom25 = az.zone_bounds_cm(180.0, 2025)
    assert (top24, bottom24) == pytest.approx((101.43, 49.752))
    # The zone moved down 0.6 percentage points of height (about 1 cm at 180 cm); its size did not change.
    assert top24 - top25 == pytest.approx(1.08) and bottom24 - bottom25 == pytest.approx(1.08)
    assert az.rule_for(2026) == az.ABS_RULES[2026] and az.rule_for(2026).top_ratio == .5575
    assert az.rule_for(2024).half_width_cm == pytest.approx(23.59)
    with pytest.raises(ValueError):
        az.rule_for(2023)


def test_implied_height_inverts_the_zone_and_rejects_inconsistent_zones():
    top, bottom = (np.array([v]) / az.CM_PER_FOOT for v in az.zone_bounds_cm(183.0, 2025))
    assert az.implied_height_cm(top, bottom, 2025)[0] == pytest.approx(183.0)
    # A 2024-ratio zone read with the 2025 rule disagrees by more than the tolerance.
    top24, bottom24 = (np.array([v]) / az.CM_PER_FOOT for v in az.zone_bounds_cm(183.0, 2024))
    assert np.isnan(az.implied_height_cm(top24 * 1.02, bottom24, 2025)[0])


def _margin(x_mid, z_mid, z_back, season=2025, height=180.0):
    top, bottom = az.zone_bounds_cm(height, season)
    margins = az.zone_margins_cm(np.array([x_mid]), np.array([z_mid]), np.array([z_back]), top, bottom, season)
    margin, edge = az.zone_margin_cm(margins)
    return margin[0], az.edge_group(edge)[0]


def test_ball_touching_the_side_edge_is_a_strike_and_beyond_is_a_ball():
    edge_x = 23.59 + az.BALL_RADIUS_CM
    assert az.abs_strike(_margin(edge_x, 75.0, 74.0)[0])[()] == 1.0
    margin, edge = _margin(edge_x + .01, 75.0, 74.0)
    assert az.abs_strike(margin)[()] == 0.0 and edge == "side" and margin == pytest.approx(-.01)


def test_bottom_must_hold_at_the_back_plane_which_sits_1_5_cm_lower():
    _, bottom = az.zone_bounds_cm(180.0, 2025)
    r = az.BALL_RADIUS_CM
    # Clears the middle-plane bottom; drops to 1 cm under it at the back plane: inside the lowered back zone.
    margin, _ = _margin(0.0, bottom - r + .2, bottom - r - 1.0)
    assert margin > 0
    # The 2024 Ryu Hyun-jin case: clears the middle plane, misses the back-plane bottom.
    margin, edge = _margin(0.0, bottom - r + .15, bottom - r - 1.5 - .78)
    assert az.abs_strike(margin)[()] == 0.0 and edge == "bottom" and margin == pytest.approx(-.78)


def test_top_is_checked_on_both_planes_without_an_offset():
    top, _ = az.zone_bounds_cm(180.0, 2024)
    margin, edge = _margin(0.0, top + az.BALL_RADIUS_CM + .3, top, season=2024)
    assert edge == "top" and margin == pytest.approx(-.3)


def test_unknown_margin_stays_unknown():
    margin, edge = _margin(np.nan, 75.0, 74.0)
    assert np.isnan(margin) and edge == "" and np.isnan(az.abs_strike(margin)[()])


def test_flip_probability_is_a_scenario_of_the_assumed_sigma():
    assert az.flip_probability([0.0], 1.0)[0] == pytest.approx(.5)
    assert az.flip_probability([2.0], 1.0)[0] == pytest.approx(az.flip_probability([-2.0], 1.0)[0])
    assert az.flip_probability([2.0], 0.0)[0] == 0.0


class StubRE:
    """Ball worth +0.05 runs, called strike -0.07 (batting team)."""

    def event_value(self, state, event):
        return {"Ball": .05, "CalledStrike": -.07}[event]


def test_abs_run_value_signs_are_consistent_for_batter_and_pitcher():
    ball, strike = arv.call_values(StubRE(), [(0, 0, 1, 1), None, (0, 3, 0, 0)])
    assert ball[0] == pytest.approx(.05) and strike[0] == pytest.approx(-.07)
    assert np.isnan(ball[1]) and np.isnan(ball[2])
    gap = .12
    # ABS ball where the umpire calls a strike 80% of the time: the batter gains 0.8 * D.
    assert arv.abs_run_value(.8, 0, .05, -.07) == pytest.approx(.8 * gap)
    # ABS strike the umpire would call a ball 90% of the time: the pitcher gains 0.9 * D.
    assert -arv.abs_run_value(.1, 1, .05, -.07) == pytest.approx(.9 * gap)
    # The expected value over the umpire's own call distribution is zero.
    p = .3
    assert p * arv.abs_run_value(p, 1, .05, -.07) + (1 - p) * arv.abs_run_value(p, 0, .05, -.07) == pytest.approx(0)
    assert arv.expected_call_change([.8, .1], [0, 1]).tolist() == pytest.approx([.8, -.9])


def test_bootstrap_by_game_resamples_games_not_pitches():
    values = [1.0, 1.0, 1.0, 1.0]
    low, high = arv.bootstrap_by_game(values, ["a", "a", "b", "b"], reps=200)
    assert low == pytest.approx(4.0) and high == pytest.approx(4.0)
    low, high = arv.bootstrap_by_game([3.0, -1.0], ["a", "b"], reps=500)
    assert low < 2.0 < high and low >= -2.0 and high <= 6.0
    assert all(math.isnan(v) for v in arv.bootstrap_by_game([], [], reps=10))


def test_probit_fit_recovers_bias_and_width():
    rng = np.random.default_rng(0)
    margin = rng.uniform(-3, 3, 20000)
    strike = (rng.random(margin.size) < np.vectorize(lambda m: .5 * (1 + math.erf((m - .2) / (.5 * math.sqrt(2)))))(margin)).astype(float)
    fit = ax.probit_fit(margin, strike)
    assert fit["bias_cm"] == pytest.approx(.2, abs=.03) and fit["sigma_cm"] == pytest.approx(.5, abs=.04)


def test_take_excludes_hit_by_pitch_and_swings():
    df = pd.DataFrame({
        "pitch_call_code": ["B", "T", "B", "S", "X"], "is_pa_terminal": [False, False, True, False, True],
        "pa_type": ["", "", "hbp", "", "in_play"], "pa_result": ["", "", "사구", "", "안타"], "parse_status": ["ok"] * 5})
    assert ax.is_take(df).tolist() == [True, True, False, False, False]


def test_states_keep_missing_values_missing():
    df = pd.DataFrame({"base_state_code_before": [3, None], "outs_before": [1, 0], "balls_before": [2, 0], "strikes_before": [1, 0]})
    assert ax.states(df) == [(3, 1, 2, 1), None]
