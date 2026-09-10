import json
from pathlib import Path
import tempfile

from visualbaseball.curated import write_game
from visualbaseball.swing_take import build_swing_take


def pitch(seq, call, balls, strikes, after_balls, after_strikes, px, pz, outs_after=0):
    return {
        "season": 2026, "game_id": "g", "inning": 1, "inning_half": "top", "event_seq": seq,
        "parse_status": "ok", "pitch_call_code": call, "is_pa_terminal": outs_after == 3,
        "pa_result": "out" if outs_after == 3 else "", "batter_name": "홍창기",
        "px": px, "pz": pz, "sz_top": 3.5, "sz_bottom": 1.5,
        "balls_before": balls, "strikes_before": strikes, "outs_before": 0,
        "base_state_code_before": 0, "balls_after": after_balls,
        "strikes_after": after_strikes, "outs_after": outs_after,
        "base_state_code_after": 0, "runs_on_pitch": 0,
    }


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    rows = [
        pitch(1, "B", 0, 0, 1, 0, 0, 2.5),
        pitch(2, "F", 1, 0, 1, 1, 1.0, 2.5),
        pitch(3, "S", 1, 1, 1, 2, 1.5, 2.5),
        pitch(4, "S", 1, 2, 0, 0, 0, 2.5, outs_after=3),
    ]
    for index, row in enumerate(rows, 1):
        row["pitch_id"] = f"p{index}"
    write_game(root, {"season": 2026, "game_id": "g"}, [], rows)

    eligible, targeted = build_swing_take(root)
    index = json.loads((root / "web/data/swing_take/2026/index.json").read_text(encoding="utf-8"))
    player = next(player for player in index["players"] if player["name"] == "홍창기")
    shard_name = player["id"][0] if player["id"][0].isdigit() else "other"
    shard = json.loads((root / f"web/data/swing_take/2026/players/{shard_name}.json").read_text(encoding="utf-8"))
    pitches = shard["players"][player["id"]]

    assert eligible == 4 and targeted == 4
    assert len(pitches["pitches"]) == 4
    assert shard["source"]["dataset"] == "data/curated/pitches"
    assert shard["source"]["schema_sha256"]
