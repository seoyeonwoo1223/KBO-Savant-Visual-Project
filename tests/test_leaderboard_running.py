import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location("running", Path(__file__).parents[1] / "scripts/refresh_leaderboard_running.py")
running = importlib.util.module_from_spec(spec)
spec.loader.exec_module(running)


def page(season="2026", series="0"):
    prefix = running.PREFIX
    return f'''<select name="{prefix}ddlSeason$ddlSeason"><option selected value="{season}">시즌</option></select>
    <select name="{prefix}ddlSeries$ddlSeries"><option selected value="{series}">종류</option></select>
    <tr><td>1</td><td><a href="/Record/Player/HitterDetail/Basic.aspx?playerId=12345">김타자</a></td><td>LG</td>
    <td data-id="GAME_CN">120</td><td data-id="SB_CN">20</td><td data-id="CS_CN">4</td></tr>'''


def test_official_running_requires_same_regular_season():
    _, rows = running.parse_page(page(), 2026)
    assert rows == [{"player_id": "12345", "name": "김타자", "team": "LG", "G": 120, "SB": 20, "CS": 4}]
    for text in [page("2025"), page(series="1"), page().replace('data-id="CS_CN"', 'data-id="changed"')]:
        with pytest.raises(ValueError):
            running.parse_page(text, 2026)
