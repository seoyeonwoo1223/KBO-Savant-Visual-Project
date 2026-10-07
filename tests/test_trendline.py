from collections import Counter
import json

from visualbaseball.trendline import FIELDS, INDEX, aggregate, build_trendline, pitch_counts


def row(**changes):
    return {"pitch_id": "p", "game_id": "20260401KTLG0", "game_date": "2026-04-01", "inning_half": "top",
            "event_seq": 1, "batter_id": "a", "batter_name": "타자", "pitcher_id": "b", "pitcher_name": "투수",
            "pitch_type_code": "FF", "pitch_type_kr": "포심", "velocity_kmh": 150, "is_swing": True,
            "is_contact": False, "px": 1, "pz": 2, "sz_bottom": 1.5, "sz_top": 3.5,
            "is_pa_terminal": True, "pa_id": "pa", "pa_type": "k", "pa_result": "삼진", **changes}


def game(**changes):
    return {"game_id": "20260401KTLG0", "is_final": True, "away_team": "KT", "home_team": "LG", **changes}


def test_missing_flags_are_excluded_from_their_denominators():
    counts = pitch_counts(row(is_swing=None, is_contact=None, px=None, velocity_kmh=None))
    assert counts[INDEX["pitches"]] == 1
    assert all(counts[INDEX[key]] == 0 for key in ["velocity_n", "swing_n", "contact_n", "location_n", "o_n", "z_n", "swstr_n"])
    counts = pitch_counts(row(is_contact=None))
    assert counts[INDEX["swings"]] == 1 and counts[INDEX["o_n"]] == 1
    assert counts[INDEX["contact_n"]] == counts[INDEX["swstr_n"]] == 0
    assert pitch_counts(row(px=10/12))[INDEX["z_n"]] == 1


def test_league_counts_each_pitch_once_and_terminal_pa_once():
    players, league = aggregate([row(), row(pitch_id="q", event_seq=2)], [game()])
    counts = league["2026-04-01"]["all"]
    assert counts[INDEX["pitches"]] == 2 and counts[INDEX["pa"]] == counts[INDEX["k"]] == 1
    for role, pid in [("pitcher", "b"), ("batter", "a")]:
        assert players[role][pid]["games"]["20260401KTLG0"]["bucket"]["all"] == counts
    assert not aggregate([row()], [game(is_final=False)])[1]
    assert not aggregate([row()], [game(away_team="퓨처스")])[1]
    historical, archived_league = aggregate([row()], [game(away_team="SK")])
    assert archived_league["2026-04-01"]["all"][INDEX["pitches"]] == 1
    assert historical["batter"]["a"]["games"]["20260401KTLG0"]["team"] == "SK"


def test_legacy_strikeouts_and_hit_by_pitch_are_not_misclassified():
    assert pitch_counts(row(pa_type=None, pa_result="삼진"), True)[INDEX["k"]] == 1
    assert pitch_counts(row(pa_type="bb", pa_result="사구"), True)[INDEX["bb"]] == 0
    assert pitch_counts(row(pa_type=None, pa_result="고의사"), True)[INDEX["bb"]] == 1
    unknown = pitch_counts(row(pa_type="out", pa_result=""), True)
    assert unknown[INDEX["pa"]] == 0 and unknown[INDEX["pa_unknown"]] == 1


def test_build_publish_and_missing_player_output_invalidates_state(tmp_path):
    from visualbaseball.curated import write_game
    from visualbaseball.metric_state import mark_built, needs_build
    write_game(tmp_path, {**game(), "season": 2026, "game_date": "2026-04-01"}, [], [{**row(), "season": 2026}])
    path = build_trendline(tmp_path)
    data = json.loads(path.read_text())
    assert data["players"]["pitcher"][0]["id"] == "b"
    league = json.loads(path.with_name("league.json").read_text())
    assert league["days"][0]["counts"][INDEX["k"]] == 1
    mark_built(tmp_path, 2026, "trendline")
    assert not needs_build(tmp_path, 2026, "trendline")
    path.parent.joinpath("pitcher/players/b.json").unlink()
    assert needs_build(tmp_path, 2026, "trendline")


def test_cli_current_exports_and_archived_only_include_trendline(tmp_path, monkeypatch):
    from visualbaseball import cli
    calls = []
    monkeypatch.setattr(cli, "_build_metric", lambda root, season, name, build: calls.append((season,name)))
    monkeypatch.setattr(cli, "build_summary", lambda root: None)
    cli._exports(tmp_path, 2026, tmp_path)
    assert (2026,"trendline") in calls
    parser = cli._arguments()
    cli._build_only(parser, parser.parse_args(["--only","trendline","--season","2019"]), tmp_path)
    assert (2019,"trendline") in calls
