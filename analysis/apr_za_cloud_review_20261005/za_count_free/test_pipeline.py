"""ZA 전용 경로가 기존 성향 보정과 분리되는지 작은 제어 모형으로 검산한다."""
import unittest
from unittest.mock import patch

import numpy as np

import run_experiment as E


class Model:
    classes_ = np.array([0, 1])

    def set_params(self, **kwargs):
        return self

    def fit(self, x, y):
        return self

    def predict_proba(self, x):
        # 추가 마지막 feature가 있으면 카운트의 영향이 드러나는 제어 모형.
        p = np.clip(.3+.05*np.nan_to_num(x[:, -1]), .1, .9)
        return np.column_stack((1-p, p))


class PipelineTests(unittest.TestCase):
    def fixture(self):
        return [dict(game_id=f"2023010{i//8+1}", decision_type="Swing" if i % 2 else "Take",
                     event="CalledStrike" if i % 4 == 0 else "Ball", x_relative=.2*i,
                     z_relative=.1, sz_top=3., sz_bottom=1.5, balls_before=i % 4, strikes_before=i % 3)
                for i in range(24)]

    def test_q_only_count_invariance(self):
        rows = self.fixture()
        with patch.object(E.old, "_classifier", return_value=Model()):
            _, free_error = E.pzone_with_controls(rows, rows, E.old.PZONE_NUMERIC)
            _, call_error = E.pzone_with_controls(rows, rows, E.zd.PZONE_UMPIRE)
        self.assertEqual(free_error, 0.)
        self.assertGreater(call_error, 0.)

    def test_extracted_propensity_runs_and_uses_original_zone_side(self):
        rows = self.fixture(); seen = []
        policy = E.propensity_only()

        def encode(train, test, categorical):
            self.assertEqual(categorical, E.zd.PSWING_CATEGORICAL)
            return np.array([[r["strikes_before"]] for r in train]), np.array([[r["strikes_before"]] for r in test])

        def qcall(train, test, fields):
            seen.append(fields)
            self.assertIn("balls_before", fields)
            self.assertIn("strikes_before", fields)
            self.assertTrue(set(r["game_id"] for r in train).isdisjoint(r["game_id"] for r in test))
            return np.array([.8 if r["strikes_before"] else .2 for r in test])

        policy.__globals__.update(encode=encode, fit_model=lambda model, x, y: model,
                                 pswing_classifier=Model, predict_pzone=qcall)
        test_q = np.array([.8 if r["strikes_before"] else .2 for r in rows])
        p, raw = policy(rows, rows, E.zd.PZONE_UMPIRE, test_q)
        self.assertEqual(len(seen), 3)
        self.assertEqual(p.shape, raw.shape)
        self.assertTrue(np.isfinite(p).all())
        self.assertTrue(((p >= 0) & (p <= 1)).all())


if __name__ == "__main__":
    unittest.main()
