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


def test_committed_curated_is_in_step_with_the_correction_table():
    """Harness gate: every table pitch is W in curated and W/V plate appearances follow the state rules.

    Fails until scripts/apply_call_corrections.py has been run and its curated output committed.
    """
    from check_call_corrections import SEASONS, check_season

    root = Path(__file__).resolve().parents[1]
    dirty = {season: result for season in SEASONS if not (result := check_season(root, season))["clean"]}
    assert not dirty, f"run scripts/apply_call_corrections.py: {dirty}"


def test_check_flags_pending_stale_and_count_errors(tmp_path, monkeypatch):
    import check_call_corrections as check

    rows = [{"pitch_id": "P1", "pa_id": "A", "pitch_number": 1, "pitch_call_code": "W", "balls_before": 0, "strikes_before": 0, "balls_after": 0, "strikes_after": 1},
            {"pitch_id": "P2", "pa_id": "A", "pitch_number": 2, "pitch_call_code": "B", "balls_before": 0, "strikes_before": 1, "balls_after": 1, "strikes_after": 1},
            {"pitch_id": "P3", "pa_id": "A", "pitch_number": 3, "pitch_call_code": "X", "balls_before": 1, "strikes_before": 1, "balls_after": 0, "strikes_after": 0},
            {"pitch_id": "Q1", "pa_id": "B", "pitch_number": 1, "pitch_call_code": "V", "balls_before": 0, "strikes_before": 0, "balls_after": 0, "strikes_after": 0},
            {"pitch_id": "Q2", "pa_id": "B", "pitch_number": 2, "pitch_call_code": "X", "balls_before": 0, "strikes_before": 0, "balls_after": 0, "strikes_after": 0}]
    monkeypatch.setattr(check, "load_rows", lambda *a, **k: rows)
    fix = {"source_code": "B", "code": "W"}
    table = {"2024": {"pitches": [{"pitch_id": "P1", **fix}, {"pitch_id": "P2", **fix}, {"pitch_id": "Q2", **fix}]}}
    result = check.check_season(tmp_path, 2024, table)
    assert (result["applied"], result["pending"], result["stale"], result["untracked_W"]) == (1, 1, 1, 0)
    assert result["count_errors"] == 1 and not result["clean"]  # PA B: V did not add a strike


def _entry(pid, **extra):
    return {"pitch_id": pid, "batter_id": "1", "pitcher_id": "2", "source_code": "B", "code": "W", "source_velocity_kmh": 140.0, **extra}


def test_naver_supplement_keeps_trackman_rows_and_trackman_rebuild_keeps_supplement():
    import build_naver_bunt_corrections as nv
    import build_trackman_bunt_corrections as tm
    trackman = {"source": "trackman", "rule": "tm", "stats": {"corrections": 2}, "pitches": [_entry("A-1"), _entry("C-1")]}
    meta = {"rule": "nv", "input": "x.csv", "stats": {"corrections": 2}}
    body, duplicates = nv.merge_season(trackman, [_entry("B-1"), _entry("C-1")], meta)
    assert duplicates == 1 and body["source"] == "trackman" and body["rule"] == "tm"
    assert [(e["pitch_id"], e.get("source")) for e in body["pitches"]] == [("A-1", None), ("B-1", "naver_relay"), ("C-1", None)]
    assert body["supplements"] == [{"source": "naver_relay", **meta}]
    # Re-running the Naver builder replaces only its own supplement.
    again, _ = nv.merge_season(body, [_entry("D-1")], meta)
    assert [e["pitch_id"] for e in again["pitches"]] == ["A-1", "C-1", "D-1"] and len(again["supplements"]) == 1
    # Re-running the TrackMan builder keeps the Naver rows and supplement.
    rebuilt = tm.season_body(again, [_entry("A-1")], {"corrections": 1})
    assert [e["pitch_id"] for e in rebuilt["pitches"]] == ["A-1", "D-1"] and rebuilt["supplements"] == again["supplements"]
    # A Naver-only season (2025-2026) is still replaced whole.
    naver_only, _ = nv.merge_season({"source": "naver_relay", "pitches": [_entry("E-1")]}, [_entry("F-1")], meta)
    assert naver_only == {"source": "naver_relay", **meta, "pitches": [_entry("F-1")]}


def test_second_naver_input_keeps_the_first_inputs_rows_and_supplement():
    """KIA home table (games K*) and non-TrackMan game table (games N*) share a TrackMan season."""
    import copy
    import build_naver_bunt_corrections as nv
    kia_meta = {"rule": "nv", "input": "kia.csv", "stats": {"corrections": 2}}
    other_meta = {"rule": "nv", "input": "non_tm.csv", "stats": {"corrections": 1}}
    trackman = {"source": "trackman", "rule": "tm", "stats": {}, "pitches": [_entry("T1-1")]}
    with_kia, _ = nv.merge_season(trackman, [_entry("K1-1"), _entry("K2-1")], kia_meta, {"K1", "K2"})
    frozen = copy.deepcopy(with_kia)
    both, duplicates = nv.merge_season(with_kia, [_entry("N1-1")], other_meta, {"N1", "N2"})
    assert with_kia == frozen and duplicates == 0                     # input is not mutated
    assert [(e["pitch_id"], e.get("source")) for e in both["pitches"]] == [
        ("K1-1", "naver_relay"), ("K2-1", "naver_relay"), ("N1-1", "naver_relay"), ("T1-1", None)]
    assert [e for e in both["pitches"] if e["pitch_id"] in ("K1-1", "K2-1", "T1-1")] == [
        {**_entry("K1-1"), "source": "naver_relay"}, {**_entry("K2-1"), "source": "naver_relay"}, _entry("T1-1")]
    assert both["supplements"] == [{"source": "naver_relay", **kia_meta}, {"source": "naver_relay", **other_meta}]
    # Re-running either input replaces only its own rows and supplement, in either order.
    again, _ = nv.merge_season(both, [_entry("N2-1")], other_meta, {"N1", "N2"})
    assert [e["pitch_id"] for e in again["pitches"]] == ["K1-1", "K2-1", "N2-1", "T1-1"]
    assert again["supplements"] == [{"source": "naver_relay", **kia_meta}, {"source": "naver_relay", **other_meta}]
    kia_again, _ = nv.merge_season(again, [_entry("K1-1")], {**kia_meta, "stats": {"corrections": 1}}, {"K1", "K2"})
    assert [e["pitch_id"] for e in kia_again["pitches"]] == ["K1-1", "N2-1", "T1-1"]
    assert [s["input"] for s in kia_again["supplements"]] == ["non_tm.csv", "kia.csv"]
    # An entry another input already holds is not written twice.
    dup, duplicates = nv.merge_season(both, [_entry("K1-1")], other_meta, {"N1", "N2"})
    assert duplicates == 1 and [e["pitch_id"] for e in dup["pitches"]].count("K1-1") == 1


def test_naver_selection_requires_the_gate_when_present():
    import build_naver_bunt_corrections as nv
    base = {"naver_code": "W", "vb_call": "B", "match_status": "matched_context"}
    assert nv.selected(base)                                        # PR #32 input: no gate column
    assert not nv.selected({**base, "match_status": "matched_without_pitcher"})
    assert nv.selected({**base, "gate": "pass"}) and nv.selected({**base, "match_status": "matched_without_pitcher", "gate": "pass"})
    assert not nv.selected({**base, "gate": "fail:count"}) and not nv.selected({**base, "vb_call": "F", "gate": "pass"})
    assert not nv.selected({**base, "match_status": "unmatched", "gate": "pass"})
