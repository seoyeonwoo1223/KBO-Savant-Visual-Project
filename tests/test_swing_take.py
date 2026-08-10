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
        # Heart take, Chase take, Chase swing, then a two-strike foul that
        # intentionally leaves the 2-2 state unchanged.
        pitch(1, "B", 0, 0, 1, 0, 0.0, 2.5),
        pitch(2, "B", 1, 0, 2, 0, 1.5, 2.5),
        pitch(3, "F", 2, 0, 2, 1, 1.5, 2.5),
        pitch(4, "S", 2, 1, 2, 2, 1.0, 2.5),
        pitch(5, "F", 2, 2, 2, 2, 1.0, 2.5),
        # The final pitch ends the inning, so its next RE288 is zero.
        pitch(6, "S", 2, 2, 0, 0, 0.0, 2.5, outs_after=3),
    ]
    pq.write_table(pa.Table.from_pylist(rows), processed / "pitches.parquet")

    eligible, targeted = build_swing_take(tmp_path)
    profile = json.loads((tmp_path / "web/data/profiles/park-junsoon.json").read_text())
    decision_rows = pq.read_table(processed / "decision_pitches.parquet").to_pylist()

    assert eligible == targeted == 6
    assert profile["overall"]["pitches"] == 6
    assert profile["overall"]["swing_pct"] == 66.667
    assert profile["overall"]["take_pct"] == 33.333
    assert profile["regions"]["Heart"]["take"]["pitches"] == 1
    assert profile["regions"]["Chase"]["take"]["pitches"] == 1
    assert profile["regions"]["Chase"]["swing"]["pitches"] == 1
    assert any(row["event_seq"] == 6 for row in decision_rows)
