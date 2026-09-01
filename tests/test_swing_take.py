from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from visualbaseball.swing_take import build_swing_take


def pitch(seq, call, balls, strikes, after_balls, after_strikes, px, pz, *, outs_after=0, runs=0):
    return {
        "season": 2026,
        "game_id": "g",
        "inning": 1,
        "inning_half": "top",
        "event_seq": seq,
        "parse_status": "ok",
        "pitch_call_code": call,
        "is_pa_terminal": outs_after == 3,
        "pa_result": "out" if outs_after == 3 else "",
        "batter_name": "박준순",
        "px": px,
        "pz": pz,
        "sz_top": 3.5,
        "sz_bottom": 1.5,
        "balls_before": balls,
        "strikes_before": strikes,
        "outs_before": 0,
        "base_state_code_before": 0,
        "balls_after": after_balls,
        "strikes_after": after_strikes,
        "outs_after": outs_after,
        "base_state_code_after": 0,
        "runs_on_pitch": runs,
    }


def test_swing_take_contract_cases(tmp_path):
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    rows = [
        pitch(1, "B", 0, 0, 1, 0, 0.0, 2.5),
        pitch(2, "B", 1, 0, 2, 0, 1.5, 2.5),
        pitch(3, "F", 2, 0, 2, 1, 1.5, 2.5),
        pitch(4, "S", 2, 1, 2, 2, 1.0, 2.5),
        pitch(5, "F", 2, 2, 2, 2, 1.0, 2.5),
        pitch(6, "S", 2, 2, 0, 0, 0.0, 2.5, outs_after=3),
    ]
    pq.write_table(pa.Table.from_pylist(rows), processed / "pitches.parquet")

    eligible, targeted = build_swing_take(tmp_path)
    index = json.loads((tmp_path / "web/data/swing_take/2026/index.json").read_text())
    player = next(player for player in index["players"] if player["name"] == "박준순")
    shard_name = player["id"][0] if player["id"][0].isdigit() else "other"
    shard = json.loads((tmp_path / f"web/data/swing_take/2026/players/{shard_name}.json").read_text())
    payload = shard["players"][player["id"]]
    pitches = payload["pitches"]
    decision_rows = pq.read_table(processed / "decision_pitches.parquet").to_pylist()

    assert eligible == targeted == 6
    assert len(pitches) == 6
    assert sum(pitch["action"] == "Swing" for pitch in pitches) == 4
    assert sum(pitch["action"] == "Take" for pitch in pitches) == 2
    assert sum(pitch["region"] == "Heart" and pitch["action"] == "Take" for pitch in pitches) == 1
    assert sum(pitch["region"] == "Chase" and pitch["action"] == "Take" for pitch in pitches) == 1
    assert sum(pitch["region"] == "Chase" and pitch["action"] == "Swing" for pitch in pitches) == 1
    assert any(row["event_seq"] == 6 for row in decision_rows)
