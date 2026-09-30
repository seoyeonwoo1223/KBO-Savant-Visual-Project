import pandas as pd

from analysis.trajectory_audit.pa_flow_audit import pitch_quality_flags


def test_record_quality_separates_structural_and_diagnostic_flags():
    pitches = pd.DataFrame({
        "pitch_id": ["p1", "p2", "p3"], "pa_id": ["a", "b", "c"],
        "game_id": ["game"] * 3, "game_pitch_number": [1, 2, 3],
        "pitch_call_code": ["B", "B", "T"], "px": [0.0, 2.0, 0.1],
        "pz": [2.0] * 3, "sz_top": [3.0] * 3, "sz_bottom": [1.0] * 3,
        "plate_x_error_cm": [0.0, 3.0, 2.0], "plate_z_error_cm": [0.0] * 3,
        "trajectory_status": ["missing", "valid", "valid"],
        "x0": [0.0, 2.0, 0.0], "y0": [50.0] * 3, "z0": [3.0] * 3,
        "vx0": [0.0] * 3, "vy0": [-100.0] * 3, "vz0": [0.0] * 3,
        "ax": [0.0] * 3, "ay": [0.0] * 3, "az": [0.0] * 3,
    })
    pas = pd.DataFrame({"pa_id": ["a", "b", "c"],
                        "flags": ["BB_CONT", "", "HALF_END"]})
    rows = pd.DataFrame({"pitch_id": pitches.pitch_id, "DUP_CONSEC": [False] * 3,
                         "DUP_TRAJ": [False] * 3})
    result = pitch_quality_flags(pitches, pas, rows, 2024)
    assert result.pitch_id.tolist() == ["p1", "p2", "p3"]
    assert result.review_level.tolist() == ["structural", "none", "diagnostic"]
    assert result["flags"].tolist() == ["BB_CONT,B_NEAR_CENTER", "", "HALF_END,PLATE_X_DISAGREE"]
