from visualbaseball.batter_stance import resolved_batter_stance


def test_batter_stance_uses_canonical_hand_and_release_matchup():
    assert resolved_batter_stance({"batter_id": "1"}, {"1": "L"}) == "L"
    assert resolved_batter_stance({"batter_id": "2", "release_x_50": -55}, {"2": "S"}) == "L"
    assert resolved_batter_stance({"batter_id": "2", "release_x_50": 55}, {"2": "S"}) == "R"
    assert resolved_batter_stance({"batter_id": "2", "batter_stance": "R", "release_x_50": -55}, {"2": "S"}) == "R"
