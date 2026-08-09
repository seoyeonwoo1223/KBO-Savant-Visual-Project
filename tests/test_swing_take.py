from pathlib import Path
import json
import tempfile

import pyarrow as pa
import pyarrow.parquet as pq

from visualbaseball.swing_take import build_swing_take


def pitch(seq, call, balls, strikes, after_balls, after_strikes, px, pz, outs_after=0, runs=0):
    return {"season": 2026, "game_id": "g", "inning": 1, "inning_half": "top", "event_seq": seq,
            "parse_status": "ok", "pitch_call_code": call, "is_pa_terminal": outs_after == 3,
            "pa_result": "out" if outs_after == 3 else "", "batter_name": "박준순",
            "px": px, "pz": pz, "sz_top": 3.5, "sz_bottom": 1.5, "balls_before": balls,
            "strikes_before": strikes, "outs_before": 0, "base_state_code_before": 0,
            "balls_after": after_balls, "strikes_after": after_strikes, "outs_after": outs_after,
            "base_state_code_after": 0, "runs_on_pitch": runs}


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory); (root / "data/processed").mkdir(parents=True)
    rows = [pitch(1, "B", 0, 0, 1, 0, 0, 2.5), pitch(2, "F", 1, 0, 1, 1, 1.0, 2.5),
            pitch(3, "S", 1, 1, 1, 2, 1.5, 2.5), pitch(4, "S", 1, 2, 0, 0, 0, 2.5, 3)]
    pq.write_table(pa.Table.from_pylist(rows), root / "data/processed/pitches.parquet")
    eligible, targeted = build_swing_take(root)
    profile = json.loads((root / "web/data/profiles/park-junsoon.json").read_text())
    assert eligible == 4 and targeted == 4
    assert profile["overall"]["pitches"] == 4
    assert profile["regions"]["Heart"]["take"]["pitches"] == 1
    assert profile["regions"]["Shadow"]["swing"]["pitches"] == 1
    assert profile["regions"]["Chase"]["swing"]["pitches"] == 1
    assert profile["re288"]["observed_states"] == 4
