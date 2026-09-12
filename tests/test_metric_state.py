from __future__ import annotations

from visualbaseball.curated import write_game
from visualbaseball.metric_state import mark_built, needs_build


def test_metric_state_is_manifest_backed_and_metric_specific(tmp_path):
    game = {"season": 2026, "game_id": "20260328HTSK0", "game_date": "2026-03-28"}
    pitch = {"season": 2026, "game_id": game["game_id"], "pitch_id": "p", "event_seq": 1}
    write_game(tmp_path, game, [], [pitch])
    assert needs_build(tmp_path, 2026, "swing_take")
    mark_built(tmp_path, 2026, "swing_take")
    assert not needs_build(tmp_path, 2026, "swing_take")
    assert needs_build(tmp_path, 2026, "blocking")
    write_game(tmp_path, game, [], [{**pitch, "pitch_id": "p2"}])
    assert needs_build(tmp_path, 2026, "swing_take")
