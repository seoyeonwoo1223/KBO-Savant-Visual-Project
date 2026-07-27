from __future__ import annotations


def validate_game(game: dict, events: list[dict], pitches: list[dict]) -> tuple[bool, str]:
    if not events or not pitches:
        return False, "No events or pitches were parsed"
    if len({event["event_seq"] for event in events}) != len(events):
        return False, "Duplicate event sequence"
    if len({pitch["pitch_id"] for pitch in pitches}) != len(pitches):
        return False, "Duplicate pitch key"
    pa_starts, half_starts = set(), set()
    for pitch in pitches:
        if not 0 <= pitch["balls_before"] <= 3 or not 0 <= pitch["strikes_before"] <= 2 or not 0 <= pitch["outs_before"] <= 2 or not 0 <= pitch["outs_after"] <= 3:
            return False, "Illegal count or outs"
        if pitch["pa_id"] not in pa_starts:
            pa_starts.add(pitch["pa_id"])
            if (pitch["balls_before"], pitch["strikes_before"]) != (0, 0): return False, "Plate appearance did not begin at 0-0"
        if pitch["pitch_call_code"] == "F" and pitch["strikes_before"] == 2 and pitch["strikes_after"] != 2 and not pitch["is_pa_terminal"]:
            return False, "Two-strike foul changed the strike count"
        half = (pitch["inning"], pitch["inning_half"])
        if half not in half_starts:
            half_starts.add(half)
            if (pitch["outs_before"], pitch["base_state_code_before"]) != (0, 0): return False, "Half-inning did not begin empty"
    last = events[-1]
    if (last["away_score_after"], last["home_score_after"]) != (game["away_score"], game["home_score"]):
        return False, "Reconstructed final score did not match official score"
    forbidden = ("spin", "rpm", "rotation")
    if any(any(token in key.lower() for token in forbidden) for pitch in pitches for key in pitch):
        return False, "Spin-rate field found"
    return True, "PASS"
