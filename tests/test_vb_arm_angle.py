"""Scientific invariants for the seasonal VB bridge and reference envelopes."""
import numpy as np
import pandas as pd
import pytest

from visualbaseball.vb_arm_angle import (
    aggregate, attach_interval, bridge_features, conformal_radius,
    fit_bridge, predict_bridge, split_groups, valid_vb, y2y_comparisons,
)


def sample(n=30):
    rng = np.random.default_rng(12)
    return pd.DataFrame({"season": 2023, "pitcher_id": [str(i % 15) for i in range(n)],
                         "pitcher_name": [f"p{i % 15}" for i in range(n)],
                         "pitcher_hand": np.where(np.arange(n) % 2, "Left", "Right"),
                         "height_cm": rng.uniform(175, 195, n), "release_x_55": rng.uniform(-85, 85, n),
                         "release_z_55": rng.uniform(145, 195, n), "vx_55": rng.uniform(-8, 8, n),
                         "vy_55": rng.uniform(-135, -110, n), "vz_55": rng.uniform(-8, 1, n),
                         "trajectory_valid": True, "source_y0": 50., "n_pitches": 120,
                         "stadium": "A"})


def test_split_entire_pitchers_deterministic_and_disjoint():
    groups = [str(i) for i in range(50)]*3
    splits = split_groups(groups)
    assert np.array_equal(sum(splits), np.ones(len(groups)))
    sets = [set(np.array(groups)[mask]) for mask in splits]
    assert [len(ids) for ids in sets] == [30, 10, 10]
    assert all(not sets[i] & sets[j] for i in range(3) for j in range(i))
    assert all(np.array_equal(a, b) for a, b in zip(splits, split_groups(groups)))


def test_cluster_conformal_uses_max_season_and_finite_sample_rank():
    # 19 clusters: ceil(20*.9)=18; a season duplicate doesn't grow sample size.
    errors = np.r_[np.arange(1, 20), [1, 1, 1]]
    groups = list(range(19))+[0, 0, 0]
    radius, scores = conformal_radius(errors, groups)
    assert radius == 18 and len(scores) == 19
    with pytest.raises(ValueError, match="Too few"):
        conformal_radius([1, 2], [1, 2])


def test_weighted_ratio_aggregation_preserves_linear_predictions():
    data = sample(60)
    data["rel_side"] = -data.release_x_55/100+.02
    data["rel_height"] = data.release_z_55/100-.04
    model = fit_bridge(data)
    individually = aggregate(predict_bridge(model, data), targets=True)
    grouped = predict_bridge(model, aggregate(data, targets=True))
    np.testing.assert_allclose(individually.pred_rel_side, grouped.pred_rel_side, atol=1e-12)
    np.testing.assert_allclose(individually.pred_rel_height, grouped.pred_rel_height, atol=1e-12)
    assert individually.n_pitches.sum() == data.n_pitches.sum()


def test_hand_mirror_gives_equal_features():
    data = sample(2)
    data.iloc[1] = data.iloc[0]
    data.loc[1, "pitcher_hand"] = "Left"
    data.loc[1, ["release_x_55", "vx_55"]] *= -1
    np.testing.assert_allclose(*bridge_features(data))


def test_invalid_geometry_missing_height_and_hand_fail_closed():
    data = sample(6)
    data.loc[1, "trajectory_valid"] = False
    data.loc[2, "height_cm"] = np.nan
    data.loc[3, "pitcher_hand"] = None
    data.loc[4, "vy_55"] = 0
    data.loc[5, "release_z_55"] = 500
    assert valid_vb(data).tolist() == [True, False, False, False, False, False]


class ConstantAngle:
    def predict(self, x):
        return np.full(len(x), 40.)


def test_interval_withholds_extrapolation_and_small_samples_not_clipped_success():
    data = sample(3)
    data["pred_rel_side"] = -data.release_x_55/100
    data["pred_rel_height"] = data.release_z_55/100
    data["source_55_share"] = 0.
    train = data.copy()
    reference = train.rename(columns={"pred_rel_side": "rel_side", "pred_rel_height": "rel_height"})
    data.loc[1, "n_pitches"] = 99
    data.loc[2, "height_cm"] = 215.
    result = attach_interval(data, ConstantAngle(), reference, train, 10., 2.)
    assert result.loc[0, "eaa_deg"] == 40
    assert result.loc[0, "reference_low_deg"] == 28
    assert result.loc[0, "reference_high_deg"] == 52
    assert result.loc[1:, "eaa_deg"].isna().all()
    assert result.loc[1:, "reference_low_deg"].isna().all()
    assert "KBO_coverage_unknown" in result.loc[0, "range_kind"]


def test_y2y_does_not_compare_nonconsecutive_years():
    data = sample(2)
    for column in ("pitcher_id", "pitcher_name", "pitcher_hand"):
        data.loc[1, column] = data.loc[0, column]
    data["season"] = [2022, 2024]
    assert y2y_comparisons(data, pd.DataFrame(), ConstantAngle()).empty


def test_unseen_park_keeps_point_but_suppresses_unjustified_range():
    data = sample(3)
    data["pred_rel_side"] = -data.release_x_55/100
    data["pred_rel_height"] = data.release_z_55/100
    data["source_55_share"] = 0.
    data["unseen_stadium"] = [True, False, False]
    data["season"] = [2024, 2025, 2026]
    reference = data.rename(columns={"pred_rel_side": "rel_side", "pred_rel_height": "rel_height"})
    result = attach_interval(data, ConstantAngle(), reference, data, 12., 2.)
    assert result.loc[0, "eaa_deg"] == 40
    assert pd.isna(result.loc[0, "reference_low_deg"])
    assert result.loc[0, "range_status"] == "unavailable_unseen_stadium_bias"
    assert result.loc[1, "range_status"] == "reference_only_future_season_unvalidated"


def test_y2y_common_park_weights_remove_stadium_composition_difference():
    # Same per-park release values in both years, different observed park mix.
    parks = pd.DataFrame({"season": [2024, 2024, 2025, 2025], "stadium": ["A", "B", "A", "B"],
                          "pitcher_id": "p", "pitcher_hand": "Right", "n_pitches": [900, 100, 100, 900],
                          "height_cm": 185., "pred_rel_side": .5, "pred_rel_height": [1.7, 1.8, 1.7, 1.8]})
    seasons = pd.DataFrame({"season": [2024, 2025], "pitcher_id": "p", "pitcher_name": "name",
                            "pitcher_hand": "Right", "n_pitches": 1000, "eaa_deg": [31., 39.],
                            "reference_low_deg": [17., 25.], "reference_high_deg": [45., 53.],
                            "future_season": [False, True], "source_plane_55_present": False})

    class HeightAngle:
        def predict(self, x):
            return x[:, 1]*50

    row = y2y_comparisons(seasons, parks, HeightAngle()).iloc[0]
    assert row.raw_change_deg == 8
    assert row.common_park_change_deg == pytest.approx(0.)
    assert row.common_parks == 2
    assert row.status == "direction_unresolved_by_reference_envelope"
    assert row.change_reference_low_deg == -20
    assert row.change_reference_high_deg == 36
    # Missing unseen-park range must not produce a fabricated difference range.
    seasons.loc[1, "reference_low_deg"] = np.nan
    row = y2y_comparisons(seasons, parks, HeightAngle()).iloc[0]
    assert row.status == "direction_unresolved_unseen_stadium_range_unavailable"
