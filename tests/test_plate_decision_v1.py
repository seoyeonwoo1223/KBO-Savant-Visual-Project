import numpy as np

from visualbaseball.plate_decision_v1 import (
    RANDOM_STATE,
    _bootstrap_logloss_improvement,
    _decision_value,
    _model_metrics,
    _region,
)


def test_region_contract_and_meatball_center():
    assert _region({"x_relative": 0.2, "z_relative": 0.3}) == "heart"
    assert _region({"x_relative": 0.8, "z_relative": 0.2}) == "shadow"
    assert _region({"x_relative": 1.5, "z_relative": 0.2}) == "chase"
    assert _region({"x_relative": 2.1, "z_relative": 0.2}) == "waste"


def test_model_metrics_rewards_better_probabilities():
    target = np.array([0, 0, 1, 1])
    good = _model_metrics(target, np.array([0.1, 0.2, 0.8, 0.9]))
    bad = _model_metrics(target, np.array([0.4, 0.4, 0.6, 0.6]))
    assert good["log_loss"] < bad["log_loss"]
    assert good["brier"] < bad["brier"]


def test_raw_decision_value_is_primary_total_and_per_100_is_normalized():
    raw, per_100 = _decision_value([{"dv": 0.2}, {"dv": -0.1}, {"dv": 0.4}, {"dv": 0.5}])
    assert raw == 1.0
    assert per_100 == 25.0


def test_vectorized_game_bootstrap_matches_cluster_resampling():
    target = np.array([0, 1, 0, 1, 1, 0])
    probability_x = np.array([0.3, 0.6, 0.4, 0.55, 0.7, 0.2])
    probability_o = np.array([0.2, 0.7, 0.3, 0.65, 0.8, 0.1])
    groups = np.array(["a", "a", "b", "b", "c", "c"])
    actual = _bootstrap_logloss_improvement(
        target, probability_x, probability_o, groups, iterations=50
    )

    loss_x = -(target * np.log(probability_x) + (1 - target) * np.log(1 - probability_x))
    loss_o = -(target * np.log(probability_o) + (1 - target) * np.log(1 - probability_o))
    deltas = loss_x - loss_o
    unique = np.unique(groups)
    rng = np.random.default_rng(RANDOM_STATE)
    selected = rng.integers(0, len(unique), size=(50, len(unique)))
    expected_samples = np.array([
        np.concatenate([deltas[groups == unique[index]] for index in draw]).mean()
        for draw in selected
    ])
    expected = tuple(float(value) for value in np.quantile(expected_samples, [0.025, 0.975]))
    assert np.allclose(actual, expected)
