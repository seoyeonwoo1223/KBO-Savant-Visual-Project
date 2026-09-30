"""Small behavioral checks: outcomes drive zones, angle changes move them, gaps stay empty."""
import numpy as np
import pandas as pd

from visualbaseball.movement_zones import (ANGLE_MAX, ANGLE_MIN, _mapping, expected_movement, fit_expectation,
                                         fit_model, normalize_time, profiles, release_angle, travel_time, with_deltas)
from visualbaseball.curated import write_game
from visualbaseball.metric_state import metric_input_hash


def test_release_proxy_and_trackman_scale_fit():
    np.testing.assert_allclose(release_angle([-50, 50, 50], [180, 180, 80]), [45, 45, -45])
    x = np.linspace(-40, 40, 500)
    y = 2 + 1.2 * x
    y[::50] += 80
    fit = _mapping(x, y)
    assert abs(fit["slope"] - 1.2) < .01 and abs(fit["intercept_cm"] - 2) < .01
    assert fit["n"] < len(x) and fit["rmse_cm"] < .01


def test_regression_profiles_respond_to_angle_and_real_outcomes():
    rng = np.random.default_rng(12)
    n = 12000
    angle = rng.uniform(20, 70, n)
    hb = 15 - angle * .1 + rng.normal(0, 2, n)
    ivb = angle * .25 + rng.normal(0, 3, n)
    probability = 1 / (1 + np.exp(-(-3 + .2 * ivb - .08 * hb)))
    frame = pd.DataFrame({"angle": angle, "hb": hb, "ivb": ivb, "hand": np.where(np.arange(n) % 2, "R", "L"),
                          "pitcher_id": np.arange(n) % 31, "velocity_kmh": 145., "px": 0., "z": 0.,
                          "balls_before": 1, "strikes_before": 1, "opposite": False, "season": 2026, "tm": False,
                          "hra": 0., "vra": 0., "flight": .4, "eligible_swing": True,
                          "whiff": rng.uniform(size=n) < probability})
    expectations = {hand: fit_expectation(frame[frame.hand == hand]) for hand in ("R", "L")}
    fitted = profiles(frame, fit_model(with_deltas(frame, expectations)), expectations)
    assert len(fitted["R"]["profiles"]) == ANGLE_MAX - ANGLE_MIN + 1
    left = fitted["L"]["profiles"]
    p45, p46 = left[45 - ANGLE_MIN], left[46 - ANGLE_MIN]
    assert left[0]["zones"] is None and left[-1]["zones"] is None
    assert p45["zones"]["high"]["whiff_pct"] > p45["zones"]["average"]["whiff_pct"] > p45["zones"]["low"]["whiff_pct"]
    assert p45["expected"]["center"] != p46["expected"]["center"]
    assert p45["zones"]["high"]["center"][1] > p45["zones"]["low"]["center"][1]
    inverted = frame.assign(whiff=~frame.whiff)
    reversed_profile = profiles(inverted, fit_model(with_deltas(inverted, expectations)), expectations)["L"]["profiles"][45 - ANGLE_MIN]
    reversed_zones = reversed_profile["zones"]
    assert reversed_zones["high"]["center"][1] < reversed_zones["low"]["center"][1]
    assert reversed_profile["expected"] == p45["expected"]  # Expectations do not depend on outcomes.
    for hand in fitted.values():
        for profile in hand["profiles"]:
            if profile["zones"]:
                cells = [set(zone["cells"]) for zone in profile["zones"].values()]
                assert not (cells[0] & cells[1] or cells[1] & cells[2] or cells[0] & cells[2])
                for zone in profile["zones"].values():
                    assert zone["cells"] and all(0 <= cell < 61*56 for cell in zone["cells"])
                    assert 0 <= zone["whiff_pct"] <= 100


def test_one_pitcher_cannot_manufacture_supported_zones():
    rng = np.random.default_rng(1)
    n = 1000
    frame = pd.DataFrame({"angle": rng.normal(45, 1, n), "hb": rng.normal(10, 2, n), "ivb": rng.normal(15, 2, n),
                          "hand": "R", "pitcher_id": "one", "velocity_kmh": 145., "px": 0., "z": 0.,
                          "balls_before": 1, "strikes_before": 1, "opposite": False, "season": 2026, "tm": False,
                          "hra": 0., "vra": 0., "flight": .4, "eligible_swing": True,
                          "whiff": rng.uniform(size=n) < .2})
    expectations = {hand: fit_expectation(frame[frame.hand == hand]) for hand in ("R", "L")}
    result = profiles(frame, fit_model(with_deltas(frame, expectations)), expectations)
    assert all(p["zones"] is None for hand in result.values() for p in hand["profiles"])
    assert all(p["expected"] is None for hand in result.values() for p in hand["profiles"])


def test_time_normalization_and_conditional_shape():
    np.testing.assert_allclose(travel_time(-100, 0, -50), .5)
    t = travel_time(-100, 20, -50)
    np.testing.assert_allclose(-100*t + 10*t*t, -50)
    assert np.isnan(travel_time(100, 20, -50))
    assert np.isnan(travel_time(-10, 20, -50))
    np.testing.assert_allclose(normalize_time([20, 20], [.4, .5]), [20, 12.8])
    rng = np.random.default_rng(7)
    angle = rng.uniform(20, 70, 4000)
    frame = pd.DataFrame({"angle": angle, "hra": 0., "vra": 0., "flight": .4,
                          "hb": 20-.2*angle+rng.normal(0, .5, len(angle)),
                          "ivb": .3*angle+rng.normal(0, .5, len(angle))})
    fitted = fit_expectation(frame)
    query = frame.iloc[:2].copy(); query["angle"] = [30, 60]
    np.testing.assert_allclose(expected_movement(query, fitted), [[14, 9], [8, 18]], atol=.05)
    assert np.diag(fitted["covariance"]).max() < .3
    assert np.diag(fitted["unconditional_covariance"]).min() > 5


def test_rebuild_hash_includes_historical_pitches_and_player_hands(tmp_path):
    game = {"season": 2019, "game_id": "20190323HTLG0"}
    write_game(tmp_path, game, [], [{"season": 2019, "game_id": game["game_id"], "pitch_id": "old"}])
    initial = metric_input_hash(tmp_path, 2026, "movement_zones")
    write_game(tmp_path, game, [], [{"season": 2019, "game_id": game["game_id"], "pitch_id": "changed"}])
    changed_pitches = metric_input_hash(tmp_path, 2026, "movement_zones")
    assert initial != changed_pitches
    bio = tmp_path / "data/curated/players/player_bio.parquet"
    bio.parent.mkdir(parents=True, exist_ok=True)
    bio.write_bytes(b"changed handedness input")  # This check tests the file dependency, not Parquet parsing.
    assert metric_input_hash(tmp_path, 2026, "movement_zones") != changed_pitches
