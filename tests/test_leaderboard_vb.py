from visualbaseball.leaderboard_vb import _hit_bases, _is_sacrifice


def test_vb_result_classification():
    assert _hit_bases("hit", "좌중이") == 2
    assert _hit_bases("hit", "우중삼") == 3
    assert _hit_bases("hit", "삼안") == 1
    assert _hit_bases("hr", "좌홈") == 4
    assert _is_sacrifice("중SF")
    assert _is_sacrifice("투희")


def test_official_running_matches_id_and_name():
    from collections import Counter
    from visualbaseball.leaderboard_vb import _batting_rows
    stats = {"1": Counter({"name": "타자", "team": "LG", "PA": 200, "AB": 180, "H": 50, "BB": 20})}
    constants = {"park": {"잠실": 1}, "weights": dict.fromkeys(["wBB", "wHBP", "w1B", "w2B", "w3B", "wHR"], 1),
                 "league_woba": .3, "scale": 1, "runs_per_win": 10, "league_runs_per_pa": .1, "league_obp": .3, "league_slg": .4}
    args = (stats, {"1": {"g"}}, {"1": Counter({"CF": 200})}, {}, constants, 2026)
    baseline, _ = _batting_rows(*args)
    rows, details = _batting_rows(*args, {"1": {"name": "타자", "SB": 20, "CS": 5}})
    assert rows[0]["SB"] == 20 and rows[0]["CS"] == 5
    assert rows[0]["SB_Runs"] == 2
    assert round(rows[0]["oWAR"] - baseline[0]["oWAR"], 2) == .2
    assert details[0]["oWAR"] == rows[0]["oWAR"]
    unmatched, _ = _batting_rows(*args, {"1": {"name": "다른 타자", "SB": 20, "CS": 5}})
    assert unmatched[0]["SB"] is None and unmatched[0]["oWAR"] == baseline[0]["oWAR"]


def test_exports_builds_current_leaderboard_only(monkeypatch, tmp_path):
    from visualbaseball import cli
    calls = []
    monkeypatch.setattr(cli, "_build_metric", lambda root, season, name, action: calls.append((season, name)))
    monkeypatch.setattr(cli, "build_summary", lambda root: None)
    cli._exports(tmp_path, 2026, tmp_path)
    assert (2026, "leaderboards") in calls
    cli._exports(tmp_path, 2025, tmp_path)
    assert (2025, "leaderboards") not in calls


def test_official_running_change_invalidates_leaderboard(tmp_path):
    from visualbaseball.curated import write_game
    from visualbaseball.metric_state import mark_built, needs_build
    game = {"season": 2026, "game_id": "20260328HTSK0", "game_date": "2026-03-28"}
    write_game(tmp_path, game, [], [{"season": 2026, "game_id": game["game_id"], "pitch_id": "p", "event_seq": 1}])
    source = tmp_path / "data/leaderboards/source/2026_running.json"
    source.parent.mkdir(parents=True)
    source.write_text('{"players": []}')
    for name in ["2026.json", "index.json"]:
        output = tmp_path / "web/data/leaderboards" / name
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text('{}')
    mark_built(tmp_path, 2026, "leaderboards")
    assert not needs_build(tmp_path, 2026, "leaderboards")
    source.write_text('{"players": [{"SB": 1}]}')
    assert needs_build(tmp_path, 2026, "leaderboards")
