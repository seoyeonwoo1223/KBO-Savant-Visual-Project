"""Join and PA gate of analysis/sbj_location/naver_kia_home_bunts.py (Naver relay -> VB pitch)."""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis" / "sbj_location"))
import naver_kia_home_bunts as k  # noqa: E402


def _vb(pa, batter, number, speed, code="B"):
    return {"pitch_id": f"G-G-{pa:03d}-{number:02d}", "pa_id": f"G-{pa:03d}", "inning": 3, "inning_half": "top",
            "batter_id": batter, "pitcher_id": "P", "pitch_number": number, "velocity_kmh": speed, "pitch_call_code": code}


def _nv(pa_no, batter, number, speed, code="B", before="0-0"):
    return {"inning": 3, "half": "top", "pa_no": pa_no, "batter": batter, "pitcher": "P", "pitch_num": number,
            "speed": str(speed), "code": code, "count_before": before}


def _with_len(naver):
    lengths = Counter((n["inning"], n["half"], n["pa_no"]) for n in naver)
    for n in naver:
        n["pa_len"] = lengths[(n["inning"], n["half"], n["pa_no"])]
    return naver


def test_batter_twice_in_a_half_inning_never_joins_the_other_pa():
    # X bats twice. His second PA's only pitch misses the speed window on Naver (143 vs 140).
    vb = [_vb(1, "X", 1, 140), _vb(2, "Y", 1, 130), _vb(3, "X", 1, 140)]
    naver = _with_len([_nv(10, "X", 1, 140, "W"), _nv(11, "Y", 1, 130), _nv(12, "X", 1, 143)])
    joined = k.join(vb, naver)
    assert joined["G-G-001-01"][1] is naver[0]
    assert joined["G-G-003-01"] == ("unmatched", None)


def test_pa_missing_on_one_side_shifts_later_pas_out_of_the_join():
    # VB lost X's first PA: X's remaining PA must not pair with Naver's first X PA and pass the gate.
    vb = [_vb(2, "Y", 1, 130), _vb(3, "X", 1, 140)]
    naver = _with_len([_nv(10, "X", 1, 140, "W"), _nv(11, "Y", 1, 130), _nv(12, "X", 1, 140)])
    joined = k.join(vb, naver)
    assert joined["G-G-002-01"] == ("unmatched", None) and joined["G-G-003-01"] == ("unmatched", None)
    assert k.pa_gate([vb[1]], joined, {"G-G-003-01"}) == "fail:unjoined_pitch"


def test_gate_recounts_with_the_bunt_foul_as_a_strike():
    vb = [_vb(1, "X", 1, 140), _vb(1, "X", 2, 141), _vb(1, "X", 3, 142, "X")]
    naver = _with_len([_nv(10, "X", 1, 140, "B", "0-0"), _nv(10, "X", 2, 141, "W", "1-0"), _nv(10, "X", 3, 142, "H", "1-1")])
    joined = k.join(vb, naver)
    assert k.pa_gate(vb, joined, {"G-G-001-02"}) == "pass"
    assert k.pa_gate(vb, joined, set()) == "fail:count"      # left as a ball, VB would read 2-0 before pitch 3
