from pathlib import Path
import json

from visualbaseball.curated import write_game
from visualbaseball.pitch_arsenal import (
    MIN_PERCENTILE_PITCHES, _load_park_factors, _pitch_code, _resolved_batter_stance, build_pitch_arsenal,
)


def _write_curated_pitches(root: Path) -> None:
    rows = []
    for number in range(4):
        rows.append({
            "season": 2026, "parse_status": "ok", "pitcher_id": "55146", "pitcher_name": "치리노스",
            "game_id": "20260328HTOB0", "inning_half": "top",
            "pitch_type_code": "FF", "pitch_type_kr": "포심", "stadium": "잠실",
            "velocity_kmh": 145 + number, "horizontal_movement_cm": 0.263 + 2.54,
            "vertical_movement_cm": 1.584 + 2.54, "x0": -1.9, "y0": 50, "z0": 6.1,
            "batter_stance": "L" if number % 2 else "R",
            "px": 0.0, "pz": 2.5, "sz_bottom": 1.5, "sz_top": 3.5,
            "is_swing": number % 2 == 0, "is_contact": number == 0,
        })
    rows.append({
        "season": 2026, "parse_status": "ok", "pitcher_id": "55146", "pitcher_name": "치리노스",
        "game_id": "20260328HTOB0", "inning_half": "top",
        "pitch_type_code": "ST", "pitch_type_kr": "스위퍼", "stadium": "잠실",
        "velocity_kmh": 132, "horizontal_movement_cm": -0.861 + 5.08,
        "vertical_movement_cm": 1.499 + 5.08, "x0": -2.0, "y0": 50, "z0": 5.9,
        "batter_stance": "R", "px": 1.0, "pz": 2.5,
        "sz_bottom": 1.5, "sz_top": 3.5, "is_swing": True, "is_contact": False,
    })
    for index, row in enumerate(rows, 1):
        row.update({"pitch_id": f"pitch-{index}", "vx0": 0, "vy0": -130, "vz0": 0, "ax": 0, "ay": 0, "az": 0})
    write_game(root, {"season": 2026, "game_id": "20260328HTOB0"}, [], rows)


def test_pitch_arsenal_builds_adjusted_profiles(tmp_path: Path):
    assert MIN_PERCENTILE_PITCHES == 50
    source_adjustments = Path(__file__).parents[1] / "data" / "park_adjustments"
    adjustment_output = tmp_path / "data" / "park_adjustments"
    adjustment_output.mkdir(parents=True)
    for source in source_adjustments.glob("*.xlsx"):
        (adjustment_output / source.name).write_bytes(source.read_bytes())
    _write_curated_pitches(tmp_path)

    pitches, players = build_pitch_arsenal(tmp_path, 2026)
    index = json.loads((tmp_path / "web/data/pitch_arsenal/2026/index.json").read_text(encoding="utf-8"))
    shard = json.loads((tmp_path / "web/data/pitch_arsenal/2026/players/5.json").read_text(encoding="utf-8"))
    profile = shard["players"]["55146"]
    four_seam, sweeper = profile["pitch_types"]

    assert (pitches, players) == (5, 1)
    assert index["players"][0]["throws"] == "R"
    assert index["players"][0]["team"] == "두산 베어스"
    assert profile["player"]["team"] == "두산 베어스"
    assert four_seam["usage"] == 80.0
    assert four_seam["horizontal_break_in"]["average"] == 1.2
    assert four_seam["ivb_in"]["average"] == 2.2
    assert four_seam["usage_by_batter"]["L"] == {"n": 2, "usage": 100.0}
    assert four_seam["usage_by_batter"]["R"] == {"n": 2, "usage": 66.7}
    assert four_seam["release"]["v_rel_ft"]["average"] == 6.1
    assert four_seam["rates"] == {"zone_pct": 100.0, "chase_pct": None, "swstr_pct": 25.0}
    assert four_seam["percentile_qualified"] is False
    assert four_seam["percentiles"]["velocity_kmh"] is None
    assert sweeper["park_factor_code"] == "SL"
    assert sweeper["horizontal_break_in"]["average"] == 1.3
    assert sweeper["ivb_in"]["average"] == 3.2
    assert sweeper["rates"] == {"zone_pct": 0.0, "chase_pct": 100.0, "swstr_pct": 100.0}


def test_legacy_duplicate_headers_use_fixed_pitch_order():
    root = Path(__file__).parents[1]
    factors = _load_park_factors(root, 2022)
    assert factors[("고척", "FF")] == (-0.226, -8.394)
    assert factors[("고척", "SL")] == (-4.434, -9.319)


def test_video_review_pitch_type_override():
    row = {
        "pitch_id": "20260708SKOB0-20260708SKOB0-037-01",
        "pitch_type_code": "FS",
        "pitch_type_kr": "포크",
    }
    assert _pitch_code(row) == "FC"


def test_batter_stance_uses_canonical_hand_and_release_matchup():
    assert _resolved_batter_stance({"batter_id": "1"}, {"1": "L"}) == "L"
    assert _resolved_batter_stance({"batter_id": "2", "release_x_50": -55}, {"2": "S"}) == "L"
    assert _resolved_batter_stance({"batter_id": "2", "release_x_50": 55}, {"2": "S"}) == "R"
    assert _resolved_batter_stance({"batter_id": "2", "batter_stance": "R", "release_x_50": -55}, {"2": "S"}) == "R"
