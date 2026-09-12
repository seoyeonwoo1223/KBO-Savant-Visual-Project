from __future__ import annotations

from visualbaseball.curated import write_game
from visualbaseball.metric_state import mark_built, needs_build


def test_metric_state_is_manifest_backed_and_metric_specific(tmp_path):
    game = {"season": 2026, "game_id": "20260328HTSK0", "game_date": "2026-03-28"}
    pitch = {"season": 2026, "game_id": game["game_id"], "pitch_id": "p", "event_seq": 1}
    write_game(tmp_path, game, [], [pitch])
    output = tmp_path / "data/metrics/swing_take/2026/decision_pitches.parquet"
    output.parent.mkdir(parents=True); output.touch()
    web = tmp_path / "web/data/swing_take/2026/index.json"
    web.parent.mkdir(parents=True); web.write_text('{"players": []}', encoding="utf-8")
    assert needs_build(tmp_path, 2026, "swing_take")
    mark_built(tmp_path, 2026, "swing_take")
    assert not needs_build(tmp_path, 2026, "swing_take")
    assert needs_build(tmp_path, 2026, "blocking")
    write_game(tmp_path, game, [], [{**pitch, "pitch_id": "p2"}])
    assert needs_build(tmp_path, 2026, "swing_take")


def test_metric_state_rebuilds_when_an_output_disappears(tmp_path):
    game = {"season": 2026, "game_id": "20260328HTSK0", "game_date": "2026-03-28"}
    write_game(tmp_path, game, [], [{"season": 2026, "game_id": game["game_id"], "pitch_id": "p", "event_seq": 1}])
    for path in (tmp_path / "data/metrics/swing_take/2026/decision_pitches.parquet", tmp_path / "web/data/swing_take/2026/index.json"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"players": []}', encoding="utf-8") if path.suffix == ".json" else path.touch()
    mark_built(tmp_path, 2026, "swing_take")
    (tmp_path / "web/data/swing_take/2026/index.json").unlink()
    assert needs_build(tmp_path, 2026, "swing_take")
