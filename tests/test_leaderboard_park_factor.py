from pathlib import Path

from openpyxl import Workbook

from visualbaseball.leaderboard_park_factor import calculate_run_park_factors


def test_calculates_run_factor_and_maps_munhak_to_incheon(tmp_path: Path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Games"
    sheet.append(("season", "is_final", "home_team", "away_team", "stadium", "home_score", "away_score"))
    sheet.append((2026, True, "SSG", "LG", "문학", 6, 4))
    sheet.append((2026, True, "LG", "SSG", "잠실", 3, 2))
    sheet.append((2026, True, "SSG", "KT", "문학", 4, 4))
    sheet.append((2026, True, "KT", "SSG", "수원", 5, 1))
    path = tmp_path / "games.xlsx"
    workbook.save(path)

    factors = calculate_run_park_factors(path, 2026)

    assert factors["인천"] == 1.636364
