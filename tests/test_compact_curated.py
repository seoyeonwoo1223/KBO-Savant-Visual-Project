from __future__ import annotations

from visualbaseball.compact_curated import compact
from visualbaseball.curated import load_rows, write_game
import pytest


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


def test_compact_month_move_removes_the_old_partition_row(tmp_path):
    game = {"season": 2026, "game_id": "20260328HTSK0", "game_date": "2026-03-28"}
    write_game(tmp_path, game, [], [{"season": 2026, "game_id": game["game_id"], "pitch_id": "march", "event_seq": 1}])
    compact(tmp_path, 2026)
    write_game(tmp_path, {**game, "game_date": "2026-04-01"}, [], [{"season": 2026, "game_id": game["game_id"], "pitch_id": "april", "event_seq": 1}])
    rows = load_rows(tmp_path, "pitches", 2026)
    assert [row["pitch_id"] for row in rows] == ["april"]


def test_compact_fails_closed_when_a_partition_is_missing(tmp_path):
    game = {"season": 2026, "game_id": "20260328HTSK0", "game_date": "2026-03-28"}
    write_game(tmp_path, game, [], [{"season": 2026, "game_id": game["game_id"], "pitch_id": "p", "event_seq": 1}])
    compact(tmp_path, 2026)
    (tmp_path / "data/curated/pitches/season=2026/month=03.parquet").unlink()
    with pytest.raises(FileNotFoundError, match="missing or corrupt"):
        write_game(tmp_path, game, [], [{"season": 2026, "game_id": game["game_id"], "pitch_id": "q", "event_seq": 1}])
