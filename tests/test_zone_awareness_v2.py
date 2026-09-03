from __future__ import annotations

import json

import pyarrow as pa
import pyarrow.parquet as pq

from visualbaseball.zone_awareness_v2 import _team_history, build_zone_awareness_v2


def test_team_history_uses_batting_team_and_preserves_transfer_order():
    assert _team_history([
        {"game_date": "2026-03-28", "event_seq": 1, "batter_team": "키움"},
        {"game_date": "2026-06-01", "event_seq": 1, "batter_team": "삼성"},
        {"game_date": "2026-06-02", "event_seq": 1, "batter_team": "삼성"},
    ]) == "KIW · SAM"


def test_team_history_falls_back_to_visual_baseball_game_id():
    assert _team_history([
        {"game_id": "20260630LTOB0", "inning_half": "top", "event_seq": 1},
        {"game_id": "20260630LTOB0", "inning_half": "bottom", "event_seq": 2},
    ]) == "LOT · DOO"


def test_staged_zone_awareness_and_web_contract(tmp_path):
    outcomes = (
        ("Swing", "S", False, False, False, "", -0.08),
        ("Swing", "F", True, False, False, "", -0.02),
        ("Swing", "X", True, True, True, "single", 0.12),
        ("Take", "B", False, False, False, "", 0.03),
        ("Take", "T", False, False, False, "", -0.04),
        ("Take", "B", False, False, True, "사구", 0.09),
    )
    rows = []
    for index in range(2_400):
        action, call, contact, in_play, terminal, result, rv = outcomes[index % 6]
        batter = index % 4
        rows.append({
            "season": 2026,
            "game_id": f"g{index // 120}",
            "event_seq": index,
            "batter_id": str(60000 + batter),
            "batter_name": f"타자{batter}",
            "batter_stance": "R" if batter % 2 else "L",
            "decision_type": action,
            "pitch_call_code": call,
            "is_contact": contact,
            "is_in_play": in_play,
            "is_pa_terminal": terminal,
            "pa_type": "hbp" if result == "사구" else "",
            "pa_result": result,
            "raw_run_value": rv + (index % 11) / 1_000,
            "x_relative": ((index % 19) - 9) / 4,
            "z_relative": (((index // 19) % 19) - 9) / 4,
            "balls_before": index % 4,
            "strikes_before": index % 3,
            "outs_before": index % 3,
            "base_state_code_before": index % 8,
            "velocity_kmh": 130 + index % 25,
            "horizontal_movement_cm": -20 + index % 41,
            "vertical_movement_cm": -10 + index % 31,
            "release_height_cm": 170 + index % 25,
            "drop_angle": 4 + index % 9,
            "pitch_type": ("직구", "슬라이더", "체인지업")[index % 3],
            "stadium": ("잠실", "문학")[index % 2],
        })
    source = tmp_path / "data" / "processed" / "decision_pitches.parquet"
    source.parent.mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist(rows), source)

    metadata = build_zone_awareness_v2(tmp_path, 2026, source)

    assert metadata["pitches"] == 2_400
    assert metadata["qualified_batters"] == 4
    assert set(metadata["model"]["branch_samples"].values()) == {400}
    leaderboard = json.loads(
        (tmp_path / "web/data/zone_awareness/2026/leaderboard.json").read_text()
    )
    assert len(leaderboard["players"]) == 4
    assert all(player["zone_awareness_plus"] is not None for player in leaderboard["players"])
    shard = json.loads(
        (tmp_path / "web/data/zone_awareness/2026/players/6.json").read_text()
    )
    cell = next(iter(shard["players"].values()))["grid"][0]
    assert abs(cell["p_whiff_if_swing"] + cell["p_contact_if_swing"] - 100) < 0.01
    assert abs(cell["p_ball_if_take"] + cell["p_called_strike_if_take"] + cell["p_hbp_if_take"] - 100) < 0.01
