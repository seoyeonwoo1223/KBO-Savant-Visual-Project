from __future__ import annotations

import json
import shutil

import pytest

from visualbaseball.compact_curated import CompactionError, compact
from visualbaseball.curated import load_rows, write_game
from visualbaseball.metric_state import mark_built, needs_build


SEASON = 2026


def _game(root, game_id: str, game_date: str, pitch_id: str = "pitch") -> None:
    write_game(
        root,
        {"season": SEASON, "game_id": game_id, "game_date": game_date},
        [],
        [{"season": SEASON, "game_id": game_id, "pitch_id": pitch_id, "event_seq": 1}],
    )


def _compact_game(root, game_id: str = "20260328HTSK0") -> str:
    _game(root, game_id, "2026-03-28")
    compact(root, SEASON)
    return game_id


def test_month_layout_ignores_leftover_legacy_shards_and_retry_cleans_them(tmp_path):
    game_id = _compact_game(tmp_path)
    directory = tmp_path / "data/curated/pitches/season=2026"
    legacy = directory / f"{game_id}.parquet"
    shutil.copy2(directory / "month=03.parquet", legacy)  # interruption after index switch

    assert [row["pitch_id"] for row in load_rows(tmp_path, "pitches", SEASON)] == ["pitch"]
    compact(tmp_path, SEASON)
    assert not legacy.exists()


def test_season_read_uses_only_indexed_months_and_fails_for_missing_ones(tmp_path):
    _compact_game(tmp_path)
    pitches = tmp_path / "data/curated/pitches/season=2026"
    shutil.copy2(pitches / "month=03.parquet", pitches / "month=10.parquet")
    assert [row["pitch_id"] for row in load_rows(tmp_path, "pitches", SEASON)] == ["pitch"]
    (tmp_path / "data/curated/events/season=2026/month=03.parquet").unlink()

    with pytest.raises(FileNotFoundError, match="compact season"):
        load_rows(tmp_path, "pitches", SEASON)


@pytest.mark.parametrize("corrupt_kind", ("events", "pitches"))
def test_corrupt_month_fails_before_any_incremental_rewrite(tmp_path, corrupt_kind):
    game_id = _compact_game(tmp_path)
    (tmp_path / f"data/curated/{corrupt_kind}/season=2026/month=03.parquet").write_bytes(b"not parquet")

    with pytest.raises(FileNotFoundError, match="compact season"):
        load_rows(tmp_path, "pitches", SEASON)
    with pytest.raises(FileNotFoundError, match="missing or corrupt"):
        _game(tmp_path, game_id, "2026-03-28", "replacement")


def test_compaction_keeps_legacy_recovery_data_when_month_is_corrupt(tmp_path):
    game_id = _compact_game(tmp_path)
    pitches = tmp_path / "data/curated/pitches/season=2026"
    legacy = pitches / f"{game_id}.parquet"
    shutil.copy2(pitches / "month=03.parquet", legacy)
    (tmp_path / "data/curated/events/season=2026/month=03.parquet").write_bytes(b"not parquet")

    with pytest.raises(CompactionError):
        compact(tmp_path, SEASON)
    assert legacy.exists()


@pytest.mark.parametrize("missing_kind", ("games", "events", "pitches"))
def test_new_game_refuses_a_corrupt_existing_target_month(tmp_path, missing_kind):
    old_game = _compact_game(tmp_path)
    (tmp_path / f"data/curated/{missing_kind}/season=2026/month=03.parquet").unlink()

    with pytest.raises(FileNotFoundError, match="missing or corrupt"):
        _game(tmp_path, "20260329HTSK0", "2026-03-29", "new-pitch")

    index = json.loads((tmp_path / "data/curated/partition-index.json").read_text(encoding="utf-8"))
    assert set(index["seasons"][str(SEASON)]["games"]) == {old_game}


@pytest.mark.parametrize("kind", ("games", "events", "pitches"))
def test_indexed_targeted_read_fails_when_its_month_file_is_missing(tmp_path, kind):
    game_id = _compact_game(tmp_path)
    (tmp_path / f"data/curated/{kind}/season=2026/month=03.parquet").unlink()

    with pytest.raises(FileNotFoundError, match="indexed compact partition is missing"):
        load_rows(tmp_path, kind, SEASON, game_id=game_id)


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def test_historical_swing_take_state_uses_the_builder_output_name(tmp_path):
    season = 2022
    write_game(
        tmp_path,
        {"season": season, "game_id": "20220328HTSK0", "game_date": "2022-03-28"},
        [],
        [{"season": season, "game_id": "20220328HTSK0", "pitch_id": "pitch", "event_seq": 1}],
    )
    _touch(tmp_path / f"data/metrics/swing_take/{season}/decision_pitches_{season}.parquet")
    output = tmp_path / f"web/data/swing_take/{season}"
    (output / "players").mkdir(parents=True)
    (output / "players/1.json").write_text("{}", encoding="utf-8")
    (output / "index.json").write_text(json.dumps({"season": season, "players": [{"id": "123"}]}), encoding="utf-8")

    mark_built(tmp_path, season, "swing_take")
    assert not needs_build(tmp_path, season, "swing_take")


def test_swing_take_state_rebuilds_when_a_referenced_player_shard_is_missing(tmp_path):
    _game(tmp_path, "20260328HTSK0", "2026-03-28")
    _touch(tmp_path / "data/metrics/swing_take/2026/decision_pitches.parquet")
    output = tmp_path / "web/data/swing_take/2026"
    (output / "players").mkdir(parents=True)
    shard = output / "players/1.json"
    shard.write_text("{}", encoding="utf-8")
    (output / "index.json").write_text(json.dumps({"season": SEASON, "players": [{"id": "123"}]}), encoding="utf-8")

    mark_built(tmp_path, SEASON, "swing_take")
    assert not needs_build(tmp_path, SEASON, "swing_take")
    shard.unlink()
    assert needs_build(tmp_path, SEASON, "swing_take")


@pytest.mark.parametrize("name", ("pitch_arsenal", "zone_profiles"))
def test_web_metric_state_rebuilds_when_a_player_shard_is_missing(tmp_path, name):
    _game(tmp_path, "20260328HTSK0", "2026-03-28")
    if name == "pitch_arsenal":
        output = tmp_path / "web/data/pitch_arsenal/2026"
        shard = output / "players/1.json"
        index = output / "index.json"
        payload = {"season": SEASON, "players": [{"id": "123", "file": "players/1.json"}]}
    else:
        output = tmp_path / "web/data/zones"
        shard = output / "2026/batter/1.json"
        index = output / "index.json"
        (output / "2026/pitcher/1.json").parent.mkdir(parents=True, exist_ok=True)
        (output / "2026/pitcher/1.json").write_text("{}", encoding="utf-8")
        payload = {"seasons": [SEASON], "players": {str(SEASON): {
            "batter": [{"id": "123", "file": "1.json"}],
            "pitcher": [{"id": "123", "file": "1.json"}],
        }}}
    shard.parent.mkdir(parents=True, exist_ok=True)
    shard.write_text("{}", encoding="utf-8")
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text(json.dumps(payload), encoding="utf-8")

    mark_built(tmp_path, SEASON, name)
    assert not needs_build(tmp_path, SEASON, name)
    shard.unlink()
    assert needs_build(tmp_path, SEASON, name)


@pytest.mark.parametrize(
    ("name", "report"),
    (("zone_decision", "data/metrics/zone_awareness/2026/report.json"),
     ("plate_decision", "data/metrics/plate_decision/2026/plate_decision_v1_report_2026.json")),
)
def test_zone_web_metric_state_rebuilds_when_a_player_shard_is_missing(tmp_path, name, report):
    _game(tmp_path, "20260328HTSK0", "2026-03-28")
    _touch(tmp_path / report)
    output = tmp_path / "web/data/zone_awareness/2026"
    shard = output / "players/12.json"
    shard.parent.mkdir(parents=True)
    shard.write_text("{}", encoding="utf-8")
    (output / "leaderboard.json").write_text(json.dumps({"players": [{"batter_id": "123"}]}), encoding="utf-8")
    (output / "teams.json").write_text("{}", encoding="utf-8")
    (output.parent / "index.json").write_text("{}", encoding="utf-8")

    mark_built(tmp_path, SEASON, name)
    assert not needs_build(tmp_path, SEASON, name)
    shard.unlink()
    assert needs_build(tmp_path, SEASON, name)
