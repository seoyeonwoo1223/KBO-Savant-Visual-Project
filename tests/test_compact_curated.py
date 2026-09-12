from __future__ import annotations

from visualbaseball.compact_curated import compact
from visualbaseball.curated import load_rows, write_game


def test_compact_replaces_game_shards_and_keeps_targeted_updates(tmp_path):
    for game_id, game_date in (("20260328HTSK0", "2026-03-28"), ("20260401HTSK0", "2026-04-01")):
        game = {"season": 2026, "game_id": game_id, "game_date": game_date}
        write_game(tmp_path, game, [], [{"season": 2026, "game_id": game_id, "pitch_id": game_id, "event_seq": 1}])
    result = compact(tmp_path, 2026)
    assert result["changed"] == 2
    assert not list((tmp_path / "data/curated/pitches/season=2026").glob("2026*.parquet"))
    assert len(load_rows(tmp_path, "pitches", 2026, game_id="20260328HTSK0")) == 1
    game = {"season": 2026, "game_id": "20260328HTSK0", "game_date": "2026-03-28"}
    write_game(tmp_path, game, [], [{"season": 2026, "game_id": game["game_id"], "pitch_id": "changed", "event_seq": 1}])
    assert load_rows(tmp_path, "pitches", 2026, game_id=game["game_id"])[0]["pitch_id"] == "changed"
