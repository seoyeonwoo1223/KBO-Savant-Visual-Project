from visualbaseball.leaderboard_vb import _hit_bases, _is_sacrifice


def test_vb_result_classification():
    assert _hit_bases("hit", "좌중이") == 2
    assert _hit_bases("hit", "우중삼") == 3
    assert _hit_bases("hit", "삼안") == 1
    assert _hit_bases("hr", "좌홈") == 4
    assert _is_sacrifice("중SF")
    assert _is_sacrifice("투희")
