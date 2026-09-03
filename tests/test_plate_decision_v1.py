import numpy as np

from visualbaseball.plate_decision_v1 import _model_metrics, _region


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
