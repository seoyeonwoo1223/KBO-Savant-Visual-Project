import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from visualbaseball.blocking import build_blocking


def test_blocking_builds_leaderboard_and_pitch_values(tmp_path: Path):
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    games, pitches = [], []
    for game_number in range(15):
        game_id = f"202604{game_number + 1:02d}AABB0"
        games.append({"game_id": game_id, "away_team": "AA", "home_team": "BB"})
        for pitch_number in range(60):
            catcher_id = "10" if pitch_number % 2 == 0 else "20"
            pitches.append({
                "season": 2026, "game_id": game_id, "pitch_id": f"{game_id}-{pitch_number}",
                "inning_half": "top" if catcher_id == "10" else "bottom",
                "catcher_id": catcher_id, "catcher_name": "포수A" if catcher_id == "10" else "포수B",
                "pitch_call_code": "B", "base_state_code_before": 1, "strikes_before": 1,
                "runner_1b_id_before": "runner", "runner_2b_id_before": None, "runner_3b_id_before": None,
                "is_wild_pitch": pitch_number == 0 and game_number % 3 == 0,
                "is_passed_ball": pitch_number == 1 and game_number % 5 == 0,
                "px": ((pitch_number % 7) - 3) * .35, "pz": 1.0 + (pitch_number % 8) * .4,
                "velocity_kmh": 120 + pitch_number % 25, "vertical_movement_cm": 10 + pitch_number % 12,
                "horizontal_movement_cm": -15 + pitch_number % 30, "drop_angle": 5.0,
                "arrival_time_s": .42, "x0": -1.8 if pitch_number % 3 else 1.8, "z0": 6.0,
                "sz_bottom": 1.5, "pitch_type_code": "FF" if pitch_number % 2 else "SL",
                "pitch_type_kr": "포심" if pitch_number % 2 else "슬라이더", "batter_stance": "L" if pitch_number % 2 else "R",
            })
    pq.write_table(pa.Table.from_pylist(games), processed / "games.parquet")
    pq.write_table(pa.Table.from_pylist(pitches), processed / "pitches.parquet")
    output = build_blocking(tmp_path, 2026)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "experimental"
    assert payload["summary"]["opportunities"] == 900
    assert len(payload["players"]) == 2
    assert payload["method"]["formula"].startswith("sum(")
    assert payload["details"]["10"]["cells"]
    table = pq.read_table(processed / "blocking_pitches.parquet")
    assert {"expected_pbwp", "actual_pbwp", "block_value", "difficulty"} <= set(table.column_names)
