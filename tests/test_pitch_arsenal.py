from pathlib import Path
import json

import xlsxwriter

from visualbaseball.pitch_arsenal import _load_park_factors, build_pitch_arsenal


def _write_pitch_workbook(path: Path) -> None:
    rows = []
    for number in range(4):
        rows.append({
            "season": 2026, "parse_status": "ok", "pitcher_id": "55146", "pitcher_name": "치리노스",
            "pitch_type_code": "FF", "pitch_type_kr": "포심", "stadium": "잠실",
            "velocity_kmh": 145 + number, "horizontal_movement_cm": 0.263 + 2.54,
            "vertical_movement_cm": 1.584 + 2.54, "x0": -1.9, "z0": 6.1,
            "batter_stance": "L" if number % 2 else "R",
            "px": 0.0, "pz": 2.5, "sz_bottom": 1.5, "sz_top": 3.5,
            "is_swing": number % 2 == 0, "is_contact": number == 0,
        })
    rows.append({
        "season": 2026, "parse_status": "ok", "pitcher_id": "55146", "pitcher_name": "치리노스",
        "pitch_type_code": "ST", "pitch_type_kr": "스위퍼", "stadium": "잠실",
        "velocity_kmh": 132, "horizontal_movement_cm": -0.861 + 5.08,
        "vertical_movement_cm": 1.499 + 5.08, "x0": -2.0, "z0": 5.9,
        "batter_stance": "R", "px": 1.0, "pz": 2.5,
        "sz_bottom": 1.5, "sz_top": 3.5, "is_swing": True, "is_contact": False,
    })
    path.parent.mkdir(parents=True)
    workbook = xlsxwriter.Workbook(path)
    sheet = workbook.add_worksheet("Pitches")
    columns = list(rows[0])
    sheet.write_row(0, 0, columns)
    for index, row in enumerate(rows, 1):
        sheet.write_row(index, 0, [row[column] for column in columns])
    workbook.close()


def test_pitch_arsenal_builds_adjusted_profiles(tmp_path: Path):
    source_adjustments = Path(__file__).parents[1] / "data" / "park_adjustments"
    adjustment_output = tmp_path / "data" / "park_adjustments"
    adjustment_output.mkdir(parents=True)
    for source in source_adjustments.glob("*.xlsx"):
        (adjustment_output / source.name).write_bytes(source.read_bytes())
    workbook = tmp_path / "exports" / "visualbaseball_savant_2026_latest.xlsx"
    _write_pitch_workbook(workbook)

    pitches, players = build_pitch_arsenal(tmp_path, 2026, workbook)
    index = json.loads((tmp_path / "web/data/pitch_arsenal/2026/index.json").read_text(encoding="utf-8"))
    shard = json.loads((tmp_path / "web/data/pitch_arsenal/2026/players/5.json").read_text(encoding="utf-8"))
    profile = shard["players"]["55146"]
    four_seam, sweeper = profile["pitch_types"]

    assert (pitches, players) == (5, 1)
    assert index["players"][0]["throws"] == "R"
    assert four_seam["usage"] == 80.0
    assert four_seam["horizontal_break_in"]["average"] == 1.2
    assert four_seam["ivb_in"]["average"] == 2.2
    assert four_seam["usage_by_batter"]["L"] == {"n": 2, "usage": 100.0}
    assert four_seam["usage_by_batter"]["R"] == {"n": 2, "usage": 66.7}
    assert four_seam["release"]["v_rel_ft"]["average"] == 6.1
    assert four_seam["rates"] == {"zone_pct": 100.0, "chase_pct": None, "swstr_pct": 25.0}
    assert four_seam["percentile_qualified"] is False
    assert sweeper["park_factor_code"] == "SL"
    assert sweeper["horizontal_break_in"]["average"] == 1.3
    assert sweeper["ivb_in"]["average"] == 3.2
    assert sweeper["rates"] == {"zone_pct": 0.0, "chase_pct": 100.0, "swstr_pct": 100.0}


def test_legacy_duplicate_headers_use_fixed_pitch_order():
    root = Path(__file__).parents[1]
    factors = _load_park_factors(root, 2022)
    assert factors[("고척", "FF")] == (-0.226, -8.394)
    assert factors[("고척", "SL")] == (-4.434, -9.319)
