from pathlib import Path
import json

from visualbaseball.curated import write_game
from visualbaseball.movement_calibration import LOCATION_COEFFICIENTS, calibrate
from visualbaseball.pitch_arsenal import (
    MIN_PERCENTILE_PITCHES, _load_park_factors, _minor_merges, _pitch_code, _resolved_batter_stance, build_pitch_arsenal,
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
    # One stadium-day has no stadium contrast, so only the plate-location term applies;
    # these pitches sit at px 0 and the zone centre, so the measured values stay.
    assert four_seam["horizontal_break_in"]["average"] == 1.1
    assert four_seam["ivb_in"]["average"] == 1.6
    assert four_seam["usage_by_batter"]["L"] == {"n": 2, "usage": 100.0}
    assert four_seam["usage_by_batter"]["R"] == {"n": 2, "usage": 66.7}
    assert four_seam["release"]["v_rel_ft"]["average"] == 6.1
    assert four_seam["rates"] == {"zone_pct": 100.0, "chase_pct": None, "swstr_pct": 25.0}
    assert four_seam["percentile_qualified"] is False
    assert four_seam["percentiles"]["velocity_kmh"] is None
    # px 1 ft: HB (4.219 + 0.5638) cm, IVB (6.579 - 0.4665) cm.
    assert sweeper["horizontal_break_in"]["average"] == 1.9
    assert sweeper["ivb_in"]["average"] == 2.4
    # Both types have at most 10 pitches, so there is no main type to merge into.
    assert four_seam["merged_from"] == [] and sweeper["minor"] is False
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


def _pitch(pitcher, stadium, day, hb, ivb, px=0.0, pz=2.5):
    return {"pitcher_id": pitcher, "stadium": stadium, "game_id": f"2026{day}XXYY0", "horizontal_movement_cm": hb,
            "vertical_movement_cm": ivb, "px": px, "pz": pz, "sz_top": 3.5, "sz_bottom": 1.5}


def test_calibration_removes_stadium_day_bias_and_location_term():
    rows = []
    for pitcher, base in (("1", -20.0), ("2", 10.0), ("3", 0.0)):
        for day, stadium, bias in (("0401", "A", 0.0), ("0402", "B", 12.0)):
            rows += [_pitch(pitcher, stadium, day, base + bias + 0.1 * i, 40.0) for i in range(40)]
    out = calibrate(rows, ["FF"] * len(rows))
    by_stadium = {name: [hb for r, (hb, _) in zip(rows, out) if r["stadium"] == name and r["pitcher_id"] == "1"] for name in "AB"}
    # Same pitcher, same pitches: the 12 cm stadium B bias is gone.
    assert abs(sum(by_stadium["B"]) / 40 - sum(by_stadium["A"]) / 40) < 0.01
    # A pitch 2 ft above the zone centre gets the TrackMan-derived location term back.
    high = calibrate(rows + [_pitch("1", "A", "0401", -20.0, 40.0, pz=4.5)], ["FF"] * (len(rows) + 1))[-1]
    level = calibrate(rows + [_pitch("1", "A", "0401", -20.0, 40.0)], ["FF"] * (len(rows) + 1))[-1]
    assert abs((high[1] - level[1]) - (-2 * LOCATION_COEFFICIENTS["ivb"][1])) < 0.05
    # Missing VB movement stays missing rather than becoming a corrected zero.
    assert calibrate([{**rows[0], "horizontal_movement_cm": None}], ["FF"]) == [(None, 40.0)]


def test_minor_pitch_types_merge_only_when_indistinguishable():
    def sample(velocity, hb, ivb, pz=2.5):
        return {"velocity": velocity, "hb": hb, "ivb": ivb, "px": 0.0, "pz": pz}
    groups = {
        "FF": [sample(145 + i % 3, -18 + i % 4, 45 + i % 4, 3.0) for i in range(60)],
        "SL": [sample(132 + i % 3, 5 + i % 4, 10 + i % 4, 2.0) for i in range(40)],
        "CU": [sample(133, 6, 11, 2.0) for _ in range(3)],     # a slider by every measure
        "CH": [sample(135, 1, 47, 5.0)],                       # matches nothing: stays apart
    }
    merges, unmerged = _minor_merges({"p": groups})
    assert merges == {("p", "CU"): "SL"}
    assert unmerged == {("p", "CH")}
    # No main type (every type small): nothing is merged or flagged.
    assert _minor_merges({"q": {"FF": groups["FF"][:5], "CH": groups["CH"]}}) == ({}, set())
