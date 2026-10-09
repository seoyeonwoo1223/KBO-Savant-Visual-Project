"""Experimental ABS Run Value: ABS calls against a pre-ABS human-umpire counterfactual.

For a taken pitch (recorded Ball or Called Strike) in an ABS season:

    p      = P(called strike | location, batter height, count, hands, pitch) from the 2022-2023 umpire model
    D      = RV(ball) - RV(called strike) at the pitch's base/out/count state (RE288, runs for the batting team)
    batter = (p - strike) * D          # actual call minus the umpire expectation, batting-team runs
    pitcher = -batter

A ball the umpire would usually have called a strike is a positive batter value; a strike the umpire
would usually have called a ball is a positive pitcher value. This is a counterfactual estimate, not a
causal effect of ABS (analysis/abs/README.md).
"""
from __future__ import annotations

import numpy as np

from .pitch_types import pitch_code

TAKE_CALLS = ("B", "T")
PITCH_GROUPS = {"FF": "fastball", "FT": "fastball", "SI": "fastball", "FC": "breaking", "SL": "breaking",
                "ST": "breaking", "CU": "breaking", "CH": "offspeed", "FS": "offspeed"}
GROUP_ORDER = ("fastball", "breaking", "offspeed", "other")
UMPIRE_FEATURES = ("x_front_cm", "z_front_cm", "height_cm", "z_front_share", "stance", "pitcher_throws",
                   "balls_before", "strikes_before", "pitch_group", "velocity_kmh",
                   "horizontal_movement_cm", "vertical_movement_cm", "season")
UMPIRE_CATEGORICAL = ("stance", "pitcher_throws", "pitch_group")
# The counterfactual umpire is the latest human-umpire season.
COUNTERFACTUAL_SEASON = 2023
UMPIRE_MODEL_PARAMS = dict(max_iter=400, learning_rate=.08, max_leaf_nodes=48, min_samples_leaf=80,
                           l2_regularization=1.0, early_stopping=True, validation_fraction=.1)
RANDOM_STATE = 7


def pitch_group(row: dict) -> str:
    return PITCH_GROUPS.get(pitch_code(row), "other")


def call_values(re, states) -> tuple[np.ndarray, np.ndarray]:
    """RV(ball) and RV(called strike) for each (bases, outs, balls, strikes) state; NaN for unknown states."""
    ball, strike = np.full(len(states), np.nan), np.full(len(states), np.nan)
    for i, state in enumerate(states):
        if state is None or state[1] >= 3:
            continue
        ball[i] = re.event_value(state, "Ball")
        strike[i] = re.event_value(state, "CalledStrike")
    return ball, strike


def abs_run_value(p_strike, strike, rv_ball, rv_strike) -> np.ndarray:
    """Batter-perspective ABS RV per take in runs; the pitcher's value is the negative."""
    p, s = np.asarray(p_strike, float), np.asarray(strike, float)
    return (p - s) * (np.asarray(rv_ball, float) - np.asarray(rv_strike, float))


def expected_call_change(p_strike, strike) -> np.ndarray:
    """+1 for a ball the umpire would have called a strike with certainty, -1 for the reverse."""
    return np.asarray(p_strike, float) - np.asarray(strike, float)


def bootstrap_by_game(values, games, reps: int = 1000, seed: int = RANDOM_STATE, level: float = .9) -> tuple[float, float]:
    """Percentile interval of the sum, resampling the player's games with replacement."""
    values, games = np.asarray(values, float), np.asarray(games)
    if values.size == 0:
        return (np.nan, np.nan)
    _, index = np.unique(games, return_inverse=True)
    per_game = np.bincount(index, weights=values)
    rng = np.random.default_rng(seed)
    draws = rng.multinomial(per_game.size, np.full(per_game.size, 1 / per_game.size), size=reps) @ per_game
    tail = (1 - level) / 2
    return float(np.quantile(draws, tail)), float(np.quantile(draws, 1 - tail))


def calibration_bins(p, y, bins: int = 10) -> list[dict]:
    p, y = np.asarray(p, float), np.asarray(y, float)
    edges = np.clip((p * bins).astype(int), 0, bins - 1)
    return [{"bin": b / bins, "n": int((edges == b).sum()),
             "mean_pred": round(float(p[edges == b].mean()), 4) if (edges == b).any() else None,
             "observed": round(float(y[edges == b].mean()), 4) if (edges == b).any() else None}
            for b in range(bins)]


def umpire_model():
    from sklearn.ensemble import HistGradientBoostingClassifier
    return HistGradientBoostingClassifier(**UMPIRE_MODEL_PARAMS, random_state=RANDOM_STATE,
                                          categorical_features=[UMPIRE_FEATURES.index(c) for c in UMPIRE_CATEGORICAL])
