from visualbaseball.teams import team_history


def test_team_history_uses_batting_team_and_preserves_transfer_order():
    assert team_history([
        {"game_date": "2026-03-28", "event_seq": 1, "batter_team": "키움"},
        {"game_date": "2026-06-01", "event_seq": 1, "batter_team": "삼성"},
        {"game_date": "2026-06-02", "event_seq": 1, "batter_team": "삼성"},
    ]) == "KIW · SAM"


def test_team_history_falls_back_to_visual_baseball_game_id():
    assert team_history([
        {"game_id": "20260630LTOB0", "inning_half": "top", "event_seq": 1},
        {"game_id": "20260630LTOB0", "inning_half": "bottom", "event_seq": 2},
    ]) == "LOT · DOO"
