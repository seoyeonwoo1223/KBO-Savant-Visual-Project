"""Ensure reference folds, seasonal grain, and transfer failure handling."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from visualbaseball.arm_angle_calibration import features, fit_reference, prepare_reference, transfer


def reference_data():
    rng = np.random.default_rng(4)
    players = np.repeat(np.arange(40), 2)
    height = np.repeat(rng.uniform(175, 200, 40), 2)
    z = rng.uniform(1.4, 1.95, 80)
    x = rng.uniform(.3, .9, 80)
    hand = np.where(players % 2, "Left", "Right")
    side = x*np.where(hand == "Left", -1, 1)
    f = pd.DataFrame({"pitcher": players.astype(str), "season": np.tile([2023, 2024], 40),
                      "pitcher_hand": hand, "height_cm": height, "rel_height": z, "rel_side": side,
                      "extension": np.nan})
    f["arm_angle"] = 20+features(f)[:, 1]*35-features(f)[:, 2]*25
    return f


def test_cross_validation_holds_out_whole_pitchers():
    _, report, oof = fit_reference(reference_data())
    assert report["model_oof"]["n"] == 80
    assert oof.groupby("pitcher").held_out_fold.nunique().eq(1).all()
    assert all(f["pitcher_overlap"] == 0 for f in report["folds"])
    assert report["model_oof"]["mae_deg"] < 2
    assert sum(f["test_rows"] for f in report["folds"]) == 80


def test_transfer_only_season_means_and_rejects_extrapolation():
    ref = reference_data(); model, _, _ = fit_reference(ref)
    pitches = pd.DataFrame({"season": [2024]*4, "pitcher_trackman_id": ["a", "a", "b", "b"],
                            "player_id": ["1", "1", "2", "2"], "player_name": ["가", "가", "나", "나"],
                            "pitcher_hand": ["Right"]*4, "trackman_id": list("1234"),
                            "release_valid": True, "height_cm": 185., "rel_height": [1.7, 1.8, .2, .2],
                            "rel_side": [.5, .7, 1.9, 1.9], "extension": [1.8, .007, 1.8, 1.8]})
    result = transfer(model, ref, pitches)
    assert len(result) == 2 and result.n_release_pitches.sum() == 4
    assert result.rel_height.iat[0] == pytest.approx(1.75)
    assert result.extension_mean_m.iat[0] == 1.8
    assert np.isfinite(result.mlb_calibrated_season_angle_deg.iat[0])
    assert pd.isna(result.mlb_calibrated_season_angle_deg.iat[1])
    assert result.transfer_status.iat[1] in {"outside_MLB_training_range", "invalid_model_prediction"}


def test_reference_requires_unique_grain_and_source_metadata():
    f = reference_data().rename(columns={"rel_height": "rel_height_m", "rel_side": "rel_side_m"})
    f["pitch_hand"] = np.where(f.pitcher_hand == "Right", "R", "L")
    f = f.drop(columns=["pitcher_hand", "extension"])
    f["reference_source_url"] = "https://baseballsavant.mlb.com/leaderboard/pitcher-arm-angles"
    f["height_source_url"] = "https://www.mlb.com/player/1"
    f["reference_source_sha256"] = "a"*64
    f["height_source_sha256"] = "b"*64
    prepared, excluded = prepare_reference(f)
    assert len(prepared) == 80 and excluded == 0
    f.loc[0, "height_cm"] = np.nan
    prepared, excluded = prepare_reference(f)
    assert len(prepared) == 79 and excluded == 1
    with pytest.raises(ValueError, match="unique"):
        prepare_reference(pd.concat([f, f.iloc[:1]]))


def test_mlb_height_parser_uses_vitals_and_requested_identity():
    path = Path(__file__).resolve().parents[1] / "scripts/collect_mlb_arm_angle_reference.py"
    spec = importlib.util.spec_from_file_location("mlb_reference_collector", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    html = b'<li class="player-header--vitals-height">6&#x27; 3&quot;/208</li>'
    assert module.parse_height(html, "453286", "https://www.mlb.com/player/max-scherzer-453286") == pytest.approx(190.5)
    with pytest.raises(ValueError, match="identity"):
        module.parse_height(html, "453286", "https://www.mlb.com/player/9999")
