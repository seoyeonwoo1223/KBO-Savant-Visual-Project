import importlib.util
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
spec = importlib.util.spec_from_file_location("fielding_source", Path(__file__).parents[1] / "scripts/refresh_leaderboard_fielding.py")
fielding = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fielding)


def test_official_innings_keep_outs_exactly():
    for text, expected in [("900", 2700), ("900 1/3", 2701), ("900 2/3", 2702), ("1/3", 1), ("2/3", 2), ("0", 0)]:
        assert fielding.innings_outs(text) == expected
    for text in ["900.1", "900 3/3", "-", ""]:
        with pytest.raises(ValueError):
            fielding.innings_outs(text)


def test_fielding_page_requires_full_same_season_scope():
    prefix = fielding.PREFIX
    text = ''.join(f'<select name="{prefix}{key}"><option selected value="{value}">선택</option></select>' for key, value in
                   [("ddlSeason$ddlSeason", "2026"), ("ddlSeries$ddlSeries", "0"), ("ddlPos$ddlPos", ""), ("ddlTeam$ddlTeam", "")])
    text += '<tr><td><a href="/Record/Player/HitterDetail/Basic.aspx?playerId=1">타자</a></td><td data-id="POS_SC">포수</td><td data-id="DEFEN_INN2_CN">900 1/3</td></tr>'
    _, rows = fielding.parse_page(text, 2026)
    assert rows == [{"player_id": "1", "name": "타자", "position": "C", "outs": 2701}]
    with pytest.raises(ValueError):
        fielding.parse_page(text, 2025)
    with pytest.raises(ValueError):
        fielding.parse_page(text.replace('value="0"', 'value="1"'), 2026)
