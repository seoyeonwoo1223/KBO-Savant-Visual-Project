import numpy as np
import pandas as pd
import pytest

from analysis.trajectory_audit.pa_flow_strict import Lost, coverage_ledger, match


def test_one_bad_velocity_does_not_discard_other_pitches_in_the_run():
    vb = pd.DataFrame({"pitch_id": ["a", "b", "c"], "pa_id": ["pa"] * 3,
                       "game_id": ["game"] * 3, "game_pitch_number": [1, 2, 3],
                       "pitch_call_code": ["B", "S", "T"],
                       "velocity_kmh": [140, 100, 142], "outs_before": [0] * 3})
    tm = pd.DataFrame({"rel_speed": [140, 141, 142], "outs_before": [0] * 3})
    lost = Lost()
    pairs = [(np.arange(3), np.arange(3))]
    matched, _ = match(vb, tm, pairs, lost, 0)
    assert matched.vi.tolist() == [0, 2]
    assert matched.run_kind.tolist() == ["equal_length_partial"] * 2
    assert lost.reason == {1: "velocity_out_of_tolerance"}

    linked = pd.DataFrame({"vb_pitch_id": ["a", "c"], "tm_trackman_id": ["t1", "t3"],
                           "tm_trackman_game_id": ["g", "g"], "tm_pitch_no": [1, 3],
                           "tm_balls_before": [0, 1], "tm_strikes_before": [0, 1],
                           "count_mismatch": [False, True], "tm_event": ["ball", ""],
                           "run_kind": matched.run_kind})
    ledger = coverage_ledger(vb, linked, lost)
    assert ledger.match_status.tolist() == ["matched", "unmatched", "matched"]
    assert ledger.unmatched_reason.tolist() == ["", "velocity_out_of_tolerance", ""]
    assert ledger.tm_pitch_id.dropna().tolist() == ["t1", "t3"]
    assert bool(ledger.count_mismatch.iloc[2])


def test_coverage_fails_if_an_unmatched_pitch_has_no_reason():
    vb = pd.DataFrame({"pitch_id": ["a"], "pa_id": ["pa"], "game_id": ["game"],
                       "game_pitch_number": [1], "pitch_call_code": ["B"]})
    with pytest.raises(ValueError, match="explicit reason"):
        coverage_ledger(vb, pd.DataFrame(columns=["vb_pitch_id"]), Lost())
