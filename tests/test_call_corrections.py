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


def test_count_table_sets_the_inherited_start_and_inserts_violation_calls_and_is_idempotent():
    # Pinch hitter inherits 0-1; a pitcher pitch-clock violation (ball) comes before pitch 2.
    pitches = _pa(["T", "B", "F", "X"], [(0, 0, 0, 1), (0, 1, 1, 1), (1, 1, 1, 2), (1, 2, 0, 0)])
    fix = {"G-001": {"batter_id": "1", "pitcher_id": "2", "source_codes": "TBFX", "start": [0, 1], "inserts": [{"before_pitch": 2, "code": "B"}]}}
    applied, recounted, skipped = correct_game(pitches, [], {}, fix)
    assert (applied, recounted, skipped) == (0, 1, [])
    assert [(r["balls_before"], r["strikes_before"], r["balls_after"], r["strikes_after"]) for r in pitches] == [
        (0, 1, 0, 2), (1, 2, 2, 2), (2, 2, 2, 2), (2, 2, 0, 0)]
    assert pitches[0]["re288_state_code_before"] == 1
    assert correct_game(pitches, [], {}, fix) == (0, 0, [])
    # A row whose pitch codes no longer match is not applied.
    other = _pa(["T", "B", "F", "X"], [(0, 0, 0, 1), (0, 1, 1, 1), (1, 1, 1, 2), (1, 2, 0, 0)])
    stale = {"G-001": {**fix["G-001"], "source_codes": "TBBX"}}
    applied, recounted, skipped = correct_game(other, [], {}, stale)
    assert (applied, recounted) == (0, 0) and skipped == ["G-001: stored plate appearance no longer matches the count table"]


def test_check_counts_the_count_table(tmp_path, monkeypatch):
    import check_call_corrections as check
    rows = _pa(["T", "X"], [(0, 1, 0, 2), (0, 2, 0, 0)])
    monkeypatch.setattr(check, "load_rows", lambda *a, **k: rows)
    table = {"2025": {"pas": [{"pa_id": "G-001", "batter_id": "1", "pitcher_id": "2", "source_codes": "TX", "start": [0, 1], "inserts": []}]}}
    result = check.check_season(tmp_path, 2025, {}, table)
    assert (result["count_table"], result["count_stale"], result["count_errors"], result["clean"]) == (1, 0, 0, True)
    unapplied = _pa(["T", "X"], [(0, 0, 0, 1), (0, 1, 0, 0)])
    monkeypatch.setattr(check, "load_rows", lambda *a, **k: unapplied)
    assert check.check_season(tmp_path, 2025, {}, table)["count_errors"] == 1
    moved = {"2025": {"pas": [{**table["2025"]["pas"][0], "source_codes": "BX"}]}}
    assert check.check_season(tmp_path, 2025, {}, moved)["count_stale"] == 1


def test_rejected_bunt_foul_goes_back_to_a_ball_take():
    pitches = _pa(["W", "B", "X"], [(0, 0, 0, 1), (0, 1, 1, 1), (1, 1, 0, 0)])
    reject = {"G-G-001-01": {"source_code": "W", "code": "B", "batter_id": "1", "pitcher_id": "2", "source_velocity_kmh": 140.0}}
    applied, recounted, skipped = correct_game(pitches, [], reject)
    assert (applied, recounted, skipped) == (1, 1, [])
    assert pitches[0]["pitch_call_code"] == "B" and pitches[0]["is_take"] and not pitches[0]["is_swing"]
    assert [(r["balls_before"], r["strikes_before"]) for r in pitches] == [(0, 0), (1, 0), (2, 0)]


def test_trackman_rebuild_keeps_naver_rejections_out():
    import build_trackman_bunt_corrections as tm
    previous = {"pitches": [_entry("A-1")], "naver_rejected": [{"pitch_id": "B-1"}]}
    body = tm.season_body(previous, [_entry("A-1"), _entry("B-1")], {"corrections": 2})
    assert [e["pitch_id"] for e in body["pitches"]] == ["A-1"] and body["naver_rejected"] == previous["naver_rejected"]
    assert body["stats"]["corrections"] == 1


def test_count_audit_call_changes_keep_other_inputs_and_never_reject_naver_rows():
    import build_naver_count_corrections as cc
    curated = {"G1-001": [{"pitch_id": "G1-G1-001-01", "pitch_number": 1, "batter_id": "1", "pitcher_id": "2", "velocity_kmh": 140.0, "is_pa_terminal": False},
                          {"pitch_id": "G1-G1-001-02", "pitch_number": 2, "batter_id": "1", "pitcher_id": "2", "velocity_kmh": 141.0, "is_pa_terminal": False}],
               "G2-001": [{"pitch_id": "G2-G2-001-01", "pitch_number": 1, "batter_id": "1", "pitcher_id": "2", "velocity_kmh": 140.0, "is_pa_terminal": False}]}
    kia = {**_entry("G2-G2-001-01"), "source": "naver_relay", "match_status": "matched_context"}
    table = {"seasons": {"2019": {"source": "trackman", "pitches": [_entry("G1-G1-001-02"), kia],
                                  "supplements": [{"source": "naver_relay", "input": "kia.csv"}]}}}
    rows = [{"pa_id": "G1-001", "calls": "1W 2B"}, {"pa_id": "G2-001", "calls": "1B"}]
    stats = cc.call_changes(table, "2019", rows, curated, "audit.csv")
    body = table["seasons"]["2019"]
    assert [(e["pitch_id"], e.get("match_status")) for e in body["pitches"]] == [("G1-G1-001-01", "naver_count_audit"), ("G2-G2-001-01", "matched_context")]
    assert [e["pitch_id"] for e in body["naver_rejected"]] == ["G1-G1-001-02"] and stats["reject_conflicts_naver_row"] == 1
    assert [x["input"] for x in body["supplements"]] == ["kia.csv", "audit.csv"]
    # A rerun on the table it wrote reports the same stats and leaves the body unchanged.
    import copy
    again = copy.deepcopy(table)
    assert cc.call_changes(again, "2019", rows, curated, "audit.csv") == stats and again == table
    # A Naver-only season (2025-2026) has no TrackMan rows to reject.
    naver_only = {"seasons": {"2025": {"source": "naver_relay", "pitches": [_entry("G2-G2-001-01")]}}}
    cc.call_changes(naver_only, "2025", [{"pa_id": "G2-001", "calls": "1B"}], curated, "audit.csv")
    assert [e["pitch_id"] for e in naver_only["seasons"]["2025"]["pitches"]] == ["G2-G2-001-01"]


def test_rerun_on_corrected_curated_keeps_table_rows():
    import build_naver_bunt_corrections as nv
    rows = [{"season": "2026", "pitch_id": "A-1", "naver_code": "W", "vb_call": "W", "match_status": "matched_id"},
            {"season": "2026", "pitch_id": "B-1", "naver_code": "W", "vb_call": "W", "match_status": "matched_id"},
            {"season": "2026", "pitch_id": "C-1", "naver_code": "W", "vb_call": "B", "match_status": "matched_id"}]
    # A-1 was applied from the table (curated now W); B-1 is a W the table never listed.
    assert [r["pitch_id"] for r in nv.picked_rows(rows, "2026", {"A-1": {}})] == ["A-1", "C-1"]


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


def test_naver_only_season_takes_a_supplement_and_keeps_it_on_main_rebuild():
    import build_naver_bunt_corrections as nv
    main_meta = {"rule": "nv", "input": "main.csv", "stats": {}}
    extra_meta = {"rule": "nv", "input": "extra.csv", "stats": {}}
    season = {"source": "naver_relay", **main_meta, "pitches": [_entry("G1-1"), _entry("G1-3")]}
    # The supplement covers game G1 too, but only rows it produced (those with `source`) are its own.
    body, _ = nv.merge_season(season, [_entry("G1-2")], extra_meta, {"G1"})
    assert [(e["pitch_id"], e.get("source")) for e in body["pitches"]] == [("G1-1", None), ("G1-2", "naver_relay"), ("G1-3", None)]
    assert body["source"] == "naver_relay" and body["input"] == "main.csv" and body["supplements"] == [{"source": "naver_relay", **extra_meta}]
    # Rebuilding the season from its main input replaces the main rows and keeps the supplement.
    rebuilt, _ = nv.merge_season(body, [_entry("G1-1")], main_meta)
    assert [(e["pitch_id"], e.get("source")) for e in rebuilt["pitches"]] == [("G1-1", None), ("G1-2", "naver_relay")]
    assert rebuilt["supplements"] == body["supplements"]


def test_naver_selection_requires_the_gate_when_present():
    import build_naver_bunt_corrections as nv
    base = {"naver_code": "W", "vb_call": "B", "match_status": "matched_context"}
    assert nv.selected(base)                                        # PR #32 input: no gate column
    assert not nv.selected({**base, "match_status": "matched_without_pitcher"})
    assert nv.selected({**base, "gate": "pass"}) and nv.selected({**base, "match_status": "matched_without_pitcher", "gate": "pass"})
    assert not nv.selected({**base, "gate": "fail:count"}) and not nv.selected({**base, "vb_call": "F", "gate": "pass"})
    assert not nv.selected({**base, "match_status": "unmatched", "gate": "pass"})
    assert nv.selected({**base, "match_status": "manual_speed_sequence", "gate": "manual"})
    assert not nv.selected({**base, "match_status": "unmatched", "gate": "manual"})
