"""실자료·파일 출력·모형 적합 없이 합성 자료로만 검증합니다.

실행: python -m unittest discover -s analysis/apr_za_cloud_review_20261005/za_count_free -p test_metrics.py
"""
import json
import unittest

import numpy as np
import pandas as pd
from numpy.testing import assert_allclose
from pandas.testing import assert_frame_equal

from metrics import METRICS, pitch_influence_functions, player_scores, score_summary
from compare import candidate_diagnostics


def fixture():
    return pd.DataFrame({
        "game_id": ["a", "a", "b", "b", "c", "c", "d", "d"],
        "batter_id": ["batter"] * 8,
        "swing": [1, 0, 1, 0, 0, 1, 0, 1],
        "p_swing": [.6, .3, .7, .4, .2, .65, .35, .55],
        "q_call": [.8, .25, .9, .3, .1, .7, .35, .6],
        "q_za": [.95, .15, .85, .25, .05, .75, .4, .55],
        "region": ["heart", "chase"] * 4,
    })


def weighted_functionals(df, weights):
    """오염분포 미분 검증에 사용할 독립적인 가중 점수 정의입니다."""
    weights = weights / weights.sum()
    r = df.swing.to_numpy() - df.p_swing.to_numpy()
    q = df.q_za.to_numpy()
    z, z_call = 2 * q - 1, 2 * df.q_call.to_numpy() - 1
    # 복소수 단계 미분에서도 허수부를 보존해 차분의 상쇄 오차를 피합니다.
    expectation = lambda x: np.dot(weights, x)
    mask = q >= .5
    return {
        "Z0_call": 100 * expectation(r * z_call),
        "Z0_free": 100 * expectation(r * z),
        "N0_free": 100 * (expectation(r * z) - expectation(r) * expectation(z)),
        "D_bin": 100 * (expectation(mask * r) / expectation(mask)
                         - expectation((~mask) * r) / expectation(~mask)),
        "D_q": 100 * (expectation(q * r) / expectation(q)
                       - expectation((1 - q) * r) / expectation(1 - q)),
        "P0_free": 100 * expectation((2 * df.swing.to_numpy() - 1) * z),
    }


class MetricsTests(unittest.TestCase):
    def test_covariance_and_soft_margin_identities(self):
        df = fixture()
        result = score_summary(df)
        r = df.swing - df.p_swing
        z = 2 * df.q_za - 1
        self.assertAlmostEqual(result["Z0_free"], result["N0_free"] + 100 * r.mean() * z.mean())
        expected_margin = 100 * ((2 * df.p_swing - 1) * z).mean()
        self.assertAlmostEqual(2 * result["Z0_free"], result["P0_free"] - expected_margin)
        cov_rq = ((r - r.mean()) * (df.q_za - df.q_za.mean())).mean()
        self.assertAlmostEqual(result["D_q"], 100 * cov_rq / (df.q_za.mean() * (1 - df.q_za.mean())))
        self.assertAlmostEqual(result["variance_q"], np.var(df.q_za, ddof=0))

    def test_binary_q_reduces_dq_to_dbin(self):
        df = fixture()
        df["q_za"] = (df.q_za >= .5).astype(float)
        result = score_summary(df)
        assert_allclose(result["D_q"], result["D_bin"], atol=1e-12)
        assert_allclose(result["D_q_se"], result["D_bin_se"], atol=1e-12)
        pi = df.q_za.mean()
        self.assertAlmostEqual(result["N0_free"], 2 * pi * (1 - pi) * result["D_bin"])
        self.assertEqual(result["ess_q_in"], result["n_in"])
        self.assertEqual(result["ess_q_out"], result["n_out"])

    def test_residual_constant_shift_invariance(self):
        df = fixture()
        shifted = df.copy()
        shifted["p_swing"] -= .1
        before, after = score_summary(df), score_summary(shifted)
        for name in ("N0_free", "D_bin", "D_q", "P0_free"):
            self.assertAlmostEqual(before[name], after[name])
        self.assertAlmostEqual(after["Z0_free"] - before["Z0_free"], 10 * (2 * df.q_za - 1).mean())
        for name in ("N0_free", "D_bin", "D_q"):
            self.assertAlmostEqual(before[f"{name}_se"], after[f"{name}_se"])

    def test_influence_functions_match_contamination_derivatives(self):
        df = fixture()
        influences = pitch_influence_functions(df)
        assert_allclose(influences.mean().to_numpy(), 0, atol=1e-12)
        n, epsilon, complex_step = len(df), 1e-6, 1e-20
        for i in range(n):
            mass = np.zeros(n)
            mass[i] = 1
            base = np.full(n, 1 / n)
            plus = weighted_functionals(df, (1 - epsilon) * base + epsilon * mass)
            minus = weighted_functionals(df, (1 + epsilon) * base - epsilon * mass)
            complex_values = weighted_functionals(df, base.astype(complex) + 1j * complex_step * (mass - base))
            for name in METRICS:
                derivative = (plus[name] - minus[name]) / (2 * epsilon)
                # 유한차분은 상쇄 오차를 고려해 소수 6자리(약 5e-7) 판정을 유지합니다.
                self.assertAlmostEqual(derivative, influences.iloc[i][name], places=6)
                # 분석의 1e-10 산술 계약은 상쇄가 없는 복소수 단계 미분으로 검증합니다.
                assert_allclose(np.imag(complex_values[name]) / complex_step,
                                influences.iloc[i][name], atol=1e-10, rtol=0)

    def test_cluster_se_uses_square_root_and_game_correction(self):
        df = fixture()
        influences = pitch_influence_functions(df)
        result = score_summary(df)
        for name in METRICS:
            totals = influences[name].groupby(df.game_id).sum()
            variance = 4 / 3 * np.square(totals).sum() / len(df) ** 2
            self.assertAlmostEqual(result[f"{name}_se"], np.sqrt(variance))
        independent = df.copy()
        independent["game_id"] = np.arange(len(df))
        independent_result = score_summary(independent)
        expected = np.std(influences.Z0_free, ddof=1) / np.sqrt(len(df))
        self.assertAlmostEqual(independent_result["Z0_free_se"], expected)

    def test_constant_residual_and_constant_q_negative_controls(self):
        constant_r = fixture()
        constant_r["swing"] = 1
        constant_r["p_swing"] = .8
        result = score_summary(constant_r)
        for name in ("N0_free", "D_bin", "D_q"):
            assert_allclose(result[name], 0, atol=1e-12)
            assert_allclose(result[f"{name}_se"], 0, atol=1e-12)
        self.assertNotEqual(result["Z0_free"], 0)
        constant_q = fixture()
        constant_q["q_za"] = .4
        result = score_summary(constant_q)
        for name in ("N0_free", "D_q"):
            assert_allclose(result[name], 0, atol=1e-12)
            assert_allclose(result[f"{name}_se"], 0, atol=1e-12)
        self.assertTrue(result["q_degenerate"])
        self.assertTrue(np.isnan(result["D_bin"]))

    def test_support_flags_ess_and_qbar_boundaries(self):
        df = pd.concat([fixture().assign(game_id=lambda x: x.game_id + str(i)) for i in range(40)], ignore_index=True)
        result = score_summary(df)
        self.assertTrue(result["eligible"])
        self.assertTrue(result["D_bin_eligible"])
        self.assertTrue(result["D_q_eligible"])
        self.assertEqual(result["n_in"] + result["n_out"], result["n"])
        self.assertAlmostEqual(result["ess_q_in"], df.q_za.sum() ** 2 / np.square(df.q_za).sum())
        thin = df.copy()
        thin["q_za"] = .2
        thin.loc[:9, "q_za"] = .8
        self.assertFalse(score_summary(thin)["D_bin_eligible"])
        low_q = df.copy()
        low_q["q_za"] = .05
        self.assertFalse(score_summary(low_q)["D_q_eligible"])
        boundary_q = df.copy()
        boundary_q["q_za"] = np.tile([0, .2], len(df) // 2)
        self.assertTrue(score_summary(boundary_q)["D_q_support"])
        thin_weight = df.copy()
        thin_weight["q_za"] = 0.
        thin_weight.loc[:31, "q_za"] = 1.
        thin_weight_result = score_summary(thin_weight)
        self.assertAlmostEqual(thin_weight_result["qbar"], .1)
        self.assertEqual(thin_weight_result["ess_q_in"], 32)
        self.assertFalse(thin_weight_result["D_q_support"])
        thin_weight["q_za"] = 1 - thin_weight.q_za
        self.assertFalse(score_summary(thin_weight)["D_q_support"])
        few_games = df.copy()
        few_games["game_id"] = np.tile(["a", "b"], len(df) // 2)
        self.assertFalse(score_summary(few_games)["D_bin_support"])
        self.assertFalse(score_summary(fixture())["eligible"])

    def test_no_mutation_order_invariance_and_player_isolation(self):
        df = fixture()
        before = df.copy(deep=True)
        baseline = player_scores(df, min_n=1, side_min=1, side_games=1)
        mixed = pd.concat([df, df.assign(batter_id="other", p_swing=.5)], ignore_index=True)
        together = player_scores(mixed, min_n=1, side_min=1, side_games=1)
        assert_frame_equal(baseline, together.iloc[[0]].reset_index(drop=True))
        reordered = player_scores(df.iloc[::-1], min_n=1, side_min=1, side_games=1)
        assert_frame_equal(baseline, reordered, check_exact=False, atol=1e-12, rtol=1e-12)
        assert_frame_equal(df, before)
        no_region = player_scores(df.drop(columns="region"), min_n=1, side_min=1, side_games=1)
        assert_frame_equal(baseline, no_region)

    def test_undefined_ratios_one_game_and_empty_players(self):
        df = fixture().assign(game_id="one", q_za=1.)
        result = score_summary(df)
        self.assertFalse(result["se_available"])
        for name in METRICS:
            self.assertTrue(np.isnan(result[f"{name}_se"]))
        self.assertTrue(np.isnan(result["D_bin"]))
        self.assertTrue(np.isnan(result["D_q"]))
        self.assertFalse(result["D_q_eligible"])
        self.assertEqual(result["ess_q_out"], 0)
        empty = player_scores(fixture().iloc[:0])
        self.assertEqual(len(empty), 0)
        self.assertIn("D_q_se", empty)
        with self.assertRaises(ValueError):
            score_summary(fixture().iloc[:0])

    def test_invalid_inputs_are_rejected(self):
        cases = [fixture().drop(columns="q_call"), fixture().assign(p_swing=np.nan),
                 fixture().assign(q_za=1.1), fixture().assign(swing=.5),
                 fixture().assign(game_id=None), fixture().assign(batter_id=None)]
        for df in cases:
            with self.assertRaises(ValueError):
                player_scores(df)
        for kwargs in ({"min_n": 0}, {"side_min": 2.5}, {"side_games": True}):
            with self.assertRaises(ValueError):
                player_scores(fixture(), **kwargs)

    def test_compare_support_and_matched_half_benchmark(self):
        batches = []
        for i in range(40):
            for strength in range(4):
                sample = fixture().assign(batter_id=f"b{strength}")
                sample["p_swing"] -= .03 * strength * (2 * sample.q_za - 1)
                sample["game_id"] = [f"{i:03}{game}" for game in sample.game_id]
                batches.append(sample)
            thin = fixture().assign(batter_id="unsupported", q_za=.2)
            shift_side = np.where(thin.game_id.isin(["a", "c"]), 1, -1)
            thin["p_swing"] += .15 * shift_side * (2 * thin.q_call - 1)
            thin["game_id"] = [f"{i:03}{game}" for game in thin.game_id]
            batches.append(thin)
        df = pd.concat(batches, ignore_index=True)
        public = pd.DataFrame({"apr": [100, 110, 120, 130], "swing_aggression": [0, 1, 2, 3]},
                              index=[f"b{i}" for i in range(4)])
        result = candidate_diagnostics(df, public)
        self.assertEqual(result["full"]["n_qualified"], 5)
        self.assertEqual(result["full"]["common_support"]["n"], 4)
        self.assertEqual(result["full"]["candidates"]["D_bin"]["n"], 4)
        self.assertAlmostEqual(result["full"]["candidates"]["D_bin"]["coverage_of_qualified"], .8)
        self.assertEqual(result["full"]["candidates"]["Z0_free"]["correlations"]["apr"]["n"], 4)
        self.assertAlmostEqual(result["full"]["all_player_pitch_weighted_means"]["D_bin"]["pitch_coverage"], .8)
        self.assertIsNone(result["full"]["candidates"]["D_q"]["mean_abs_point_delta_vs_Z0_call"])
        self.assertEqual(result["half_split"]["common_support"]["n"], 4)
        paired = result["half_split"]["candidates"]["D_bin"]
        self.assertEqual(paired["n"], 4)
        self.assertEqual(paired["Z0_call_same_ids"]["n"], 4)
        codes = pd.Categorical(df.game_id, categories=sorted(df.game_id.unique())).codes
        halves = [player_scores(df.loc[codes % 2 == side], min_n=150, side_min=25, side_games=5)
                  .set_index("batter_id") for side in (0, 1)]
        ids = [f"b{i}" for i in range(4)]
        expected = np.corrcoef(halves[0].loc[ids, "Z0_call"], halves[1].loc[ids, "Z0_call"])[0, 1]
        self.assertAlmostEqual(paired["Z0_call_same_ids"]["pearson"], expected)
        self.assertAlmostEqual(paired["Z0_call_same_ids"]["spearman_brown"], 2 * expected / (1 + expected))
        # 모든 NaN은 None으로 변환되어 엄격한 JSON 직렬화가 가능합니다.
        json.dumps(result, allow_nan=False)

    def test_compare_global_game_split_empty_and_constant_controls(self):
        df = fixture().assign(game_id=lambda x: "game" + x.game_id)
        before = df.copy(deep=True)
        public = pd.DataFrame({"apr": [100.], "swing_aggression": [0.]}, index=["batter"])
        result = candidate_diagnostics(df, public)
        shuffled = candidate_diagnostics(df.iloc[::-1], public)
        self.assertEqual(result["half_split"]["n_games"], [2, 2])
        self.assertEqual(result["half_split"]["n_pitches"], shuffled["half_split"]["n_pitches"])
        self.assertEqual(result["full"]["n_qualified"], 0)
        self.assertIsNone(result["full"]["candidates"]["Z0_call"]["correlations"]["apr"]["pearson"])
        assert_frame_equal(df, before)
        empty = candidate_diagnostics(df.iloc[:0], public)
        self.assertEqual(empty["full"]["n_players"], 0)
        self.assertEqual(empty["half_split"]["n_games"], [0, 0])
        self.assertIsNone(empty["full"]["all_player_pitch_weighted_means"]["Z0_call"]["value"])
        json.dumps(empty, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
