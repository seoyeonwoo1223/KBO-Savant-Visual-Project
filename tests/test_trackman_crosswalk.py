import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

spec = importlib.util.spec_from_file_location("crosswalk", Path(__file__).parents[1] / "scripts" / "build_trackman_id_crosswalk.py")
crosswalk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crosswalk)


def test_accepts_a_dominant_one_to_one_pair_with_a_different_id():
    accepted, rejected = crosswalk.accept_pairs({("658792", "53546"): 300, ("658792", "50001"): 3, ("50001", "50001"): 200})
    pairs = {item["trackman_id"]: item["visualbaseball_id"] for item in accepted}
    assert pairs == {"658792": "53546", "50001": "50001"}
    assert not next(item for item in accepted if item["trackman_id"] == "658792")["same_id"]
    assert rejected == []


def test_rejects_thin_split_and_many_to_one_pairs():
    counts = {("1", "10"): 5,                      # too few aligned pitches
              ("2", "20"): 60, ("2", "21"): 40,    # split across two VB IDs
              ("3", "30"): 50, ("4", "30"): 50}    # two TrackMan IDs claim one VB ID
    accepted, rejected = crosswalk.accept_pairs(counts)
    assert accepted == []
    reasons = {item["trackman_id"]: item["reasons"] for item in rejected}
    assert reasons["1"] == ["support"]
    assert "share" in reasons["2"]
    assert all("reverse_share" in reasons[tm] or reasons[tm] == ["many_to_one"] for tm in ("3", "4"))


def test_a_run_never_drops_a_season_written_earlier(tmp_path, monkeypatch):
    # A season-scoped run used to overwrite the file with that season alone.
    (tmp_path / "data" / "tracking").mkdir(parents=True)
    summary = {"seasons": {"2019": {"sha256": "a"}, "2024": {"sha256": "b"}}}
    (tmp_path / "data" / "tracking" / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    monkeypatch.setattr(crosswalk, "build_season", lambda root, season: {"roles": {}})
    monkeypatch.setattr(sys, "argv", ["build", "--root", str(tmp_path), "--seasons", "2024"])
    with pytest.raises(SystemExit):
        crosswalk.main()
    monkeypatch.setattr(sys, "argv", ["build", "--root", str(tmp_path)])
    crosswalk.main()
    written = json.loads((tmp_path / "data" / "tracking" / "player_id_crosswalk.json").read_text(encoding="utf-8"))
    assert sorted(written["seasons"]) == ["2019", "2024"]
    assert written["seasons"]["2024"]["trackman_sha256"] == "b"


def test_alignment_follows_plate_appearance_order_and_checks_state_without_ids():
    tm = pd.DataFrame({
        "trackman_game_id": "g", "date": "20240401", "inning": 1, "half": "top",
        "pitch_no": [1, 2, 3, 4], "pitch_of_pa": [1, 2, 1, 1],
        "pitcher_trackman_id": ["658792", "658792", "1", "2"], "batter_trackman_id": ["A", "A", "B", "C"],
        "balls_before": [0, 1, 0, 0], "strikes_before": [0, 0, 0, 0], "outs_before": [0, 0, 1, 2]})
    tm = pd.concat([tm, tm.assign(pitch_no=5, pitcher_trackman_id="3", batter_trackman_id="D", pitch_of_pa=1, outs_before=2).iloc[[0]]])
    vb = pd.DataFrame({
        "game_id": "20240401XXYY0", "date": "20240401", "inning": 1, "half": "top",
        # Plate-appearance numbers skip non-pitch events, so only their order matters.
        "pa_seq": [3, 3, 5, 8, 9], "pitch_of_pa": [1, 2, 1, 1, 1],
        "pitcher_id": ["53546", "53546", "1", "2", "3"], "batter_id": ["a", "a", "b", "c", "d"],
        "balls_before": [0, 1, 0, 0, 0], "strikes_before": [0, 0, 0, 0, 1], "outs_before": [0, 0, 1, 2, 2]})
    games = crosswalk.map_games(tm, vb)
    assert games == {"g": "20240401XXYY0"}
    aligned = crosswalk.align_pitches(tm, vb, games).sort_values("pitch_no")
    assert list(zip(aligned.pitcher_trackman_id, aligned.pitcher_id)) == [("658792", "53546"), ("658792", "53546"), ("1", "1"), ("2", "2"), ("3", "3")]
    assert list(aligned.state_agrees) == [True, True, True, True, False]
