import sys
from pathlib import Path

from visualbaseball.state_machine import GameState

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from apply_call_corrections import correct_game  # noqa: E402


def test_bunt_swing_and_miss_adds_a_strike():
    state = GameState()
    state.apply_non_terminal_pitch("V")
    state.apply_non_terminal_pitch("W")
    assert (state.balls, state.strikes) == (0, 2)


def _pa(codes, counts):
    rows = []
    for number, (code, (b0, s0, b1, s1)) in enumerate(zip(codes, counts), 1):
        rows.append({"pitch_id": f"G-G-001-{number:02d}", "pa_id": "G-001", "pitch_number": number, "event_seq": number,
                     "pitch_call_code": code, "batter_id": "1", "pitcher_id": "2", "velocity_kmh": 140.0, "pa_result": "삼진",
                     "balls_before": b0, "strikes_before": s0, "balls_after": b1, "strikes_after": s1,
                     "re24_state_code_before": 0, "re24_state_code_after": 0})
    return rows


def test_correct_game_recodes_bunt_foul_recounts_v_and_is_idempotent():
    # Stored with the old rules: B counted as a ball, V ignored.
    pitches = _pa(["B", "V", "B", "S"], [(0, 0, 1, 0), (1, 0, 1, 0), (1, 0, 2, 0), (2, 0, 0, 0)])
    events = [{"event_type": "pitch", "event_seq": r["event_seq"], "event_code": r["pitch_call_code"]} for r in pitches]
    fix = {"G-G-001-01": {"source_code": "B", "code": "W", "batter_id": "1", "pitcher_id": "2", "source_velocity_kmh": 140.0}}
    applied, recounted, skipped = correct_game(pitches, events, fix)
    assert (applied, recounted, skipped) == (1, 1, [])
    assert [r["pitch_call_code"] for r in pitches] == ["W", "V", "B", "S"]
    assert [(r["balls_before"], r["strikes_before"]) for r in pitches] == [(0, 0), (0, 1), (0, 2), (1, 2)]
    assert not pitches[0]["is_swing"] and not pitches[0]["is_take"] and events[0]["event_code"] == "W"
    assert correct_game(pitches, events, fix) == (0, 0, [])


def test_correct_game_skips_pa_whose_counts_follow_neither_rule():
    pitches = _pa(["B", "S"], [(0, 0, 0, 1), (0, 1, 0, 0)])
    assert correct_game(pitches, [], {}) == (0, 0, [])
    pitches = _pa(["V", "S"], [(0, 0, 1, 0), (1, 0, 0, 0)])
    applied, recounted, skipped = correct_game(pitches, [], {})
    assert (applied, recounted) == (0, 0) and skipped == ["G-001: stored counts differ from parser rules"]
