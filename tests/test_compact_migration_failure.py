"""Migration failure window: a bad monthly write must never cost the legacy shards.

Every case here damages a partition *inside* `compact()`, between the monthly write
and the legacy cleanup. Corrupting a month after a successful migration exercises
the read guard instead, and leaves the window that actually deletes data untested.
"""
from __future__ import annotations

import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from visualbaseball import compact_curated
from visualbaseball.compact_curated import CompactionError, compact
from visualbaseball.curated import SCHEMAS, load_rows, write_game


SEASON = 2026
GAMES = (("20260328HTSK0", "2026-03-28"), ("20260402LGOB0", "2026-04-02"))


def _seed(root):
    for game_id, game_date in GAMES:
        write_game(
            root,
            {"season": SEASON, "game_id": game_id, "game_date": game_date, "stadium": "S"},
            [{"game_id": game_id, "event_seq": 1, "inning": 1, "event_type": "PA", "description": "d" * 300}],
            [{"season": SEASON, "game_id": game_id, "pitch_id": f"{game_id}-1", "event_seq": 1,
              "batter_name": "b" * 300, "pitcher_name": "p" * 300, "px": 0.1, "pz": 2.4}],
        )


def _legacy_paths(root):
    return [root / f"data/curated/{kind}/season={SEASON}/{game_id}.parquet"
            for kind in SCHEMAS for game_id, _ in GAMES]


def _zero_byte(path):
    path.write_bytes(b"")


def _invalid_bytes(path):
    path.write_bytes(b"not a parquet file at all")


def _corrupt_pages(path):
    """Damage data pages but leave the header magic and the footer intact."""
    raw = bytearray(path.read_bytes())
    assert len(raw) > 3000, "seed rows are too small to corrupt pages without touching the footer"
    for offset in range(400, 3000):
        raw[offset] ^= 0xFF
    path.write_bytes(bytes(raw))


def _wrong_schema(path):
    pq.write_table(pa.table({"unrelated": [1, 2, 3]}), path)


def _drop_rows(path):
    """Valid Parquet, correct schema, silently missing rows."""
    table = pq.ParquetFile(path).read()
    pq.write_table(table.slice(0, 0), path)


CORRUPTIONS = {
    "zero_byte": _zero_byte,
    "invalid_bytes": _invalid_bytes,
    "corrupt_pages": _corrupt_pages,
    "wrong_schema": _wrong_schema,
    "dropped_rows": _drop_rows,
}


def _compact_with_damage(root, damage, target_kind="pitches", target_month="03"):
    """Run compact() and damage one partition the instant it is written."""
    original = compact_curated._atomic_parquet
    applied = []

    def failing_write(path, rows, schema):
        original(path, rows, schema)
        if path.name == f"month={target_month}.parquet" and f"/{target_kind}/" in str(path):
            damage(path)
            applied.append(path)

    compact_curated._atomic_parquet = failing_write
    try:
        with pytest.raises(CompactionError):
            compact(root, SEASON)
    finally:
        compact_curated._atomic_parquet = original
    assert applied, "the corruption hook never fired; the write path moved"


@pytest.mark.parametrize("name", sorted(CORRUPTIONS))
@pytest.mark.parametrize("kind", sorted(SCHEMAS))
def test_damaged_monthly_write_aborts_and_keeps_every_legacy_shard(tmp_path, name, kind):
    _seed(tmp_path)
    legacy = _legacy_paths(tmp_path)
    assert all(path.is_file() for path in legacy)

    _compact_with_damage(tmp_path, CORRUPTIONS[name], target_kind=kind)

    missing = [str(path.relative_to(tmp_path)) for path in legacy if not path.is_file()]
    assert not missing, f"legacy shards deleted after a failed migration: {missing}"
    index = json.loads((tmp_path / "data/curated/partition-index.json").read_text(encoding="utf-8"))
    assert index.get("layout") != "month", "index switched to month layout despite a failed migration"


@pytest.mark.parametrize("name", sorted(CORRUPTIONS))
def test_reads_fail_closed_while_a_damaged_partition_is_present(tmp_path, name):
    _seed(tmp_path)
    _compact_with_damage(tmp_path, CORRUPTIONS[name])

    # The index never switched, so reads still resolve through the retained legacy
    # shards and return complete data rather than the half-written month.
    rows = load_rows(tmp_path, "pitches", SEASON)
    assert sorted(row["game_id"] for row in rows) == sorted(game_id for game_id, _ in GAMES)


@pytest.mark.parametrize("name", sorted(CORRUPTIONS))
def test_rerunning_after_a_failed_migration_succeeds(tmp_path, name):
    _seed(tmp_path)
    _compact_with_damage(tmp_path, CORRUPTIONS[name])

    result = compact(tmp_path, SEASON)

    assert result["changed"] == len(GAMES)
    assert not [path for path in _legacy_paths(tmp_path) if path.is_file()]
    rows = load_rows(tmp_path, "pitches", SEASON)
    assert sorted(row["game_id"] for row in rows) == sorted(game_id for game_id, _ in GAMES)


def test_interrupted_migration_does_not_double_count_rows_on_a_season_read(tmp_path):
    """Valid monthly files plus retained legacy shards must not both be read."""
    _seed(tmp_path)
    original = compact_curated.verify_partitions
    compact_curated.verify_partitions = lambda *args, **kwargs: (_ for _ in ()).throw(
        CompactionError("interrupted before the index switch"))
    try:
        with pytest.raises(CompactionError):
            compact(tmp_path, SEASON)
    finally:
        compact_curated.verify_partitions = original

    assert (tmp_path / f"data/curated/pitches/season={SEASON}/month=03.parquet").is_file()
    assert all(path.is_file() for path in _legacy_paths(tmp_path))
    rows = load_rows(tmp_path, "pitches", SEASON)
    assert sorted(row["game_id"] for row in rows) == sorted(game_id for game_id, _ in GAMES)


def test_interruption_between_index_write_and_cleanup_is_resumable(tmp_path):
    _seed(tmp_path)
    original = compact_curated._legacy_shards
    compact_curated._legacy_shards = lambda root, season: []  # die before cleanup
    try:
        compact(tmp_path, SEASON)
    finally:
        compact_curated._legacy_shards = original

    assert all(path.is_file() for path in _legacy_paths(tmp_path))
    assert compact(tmp_path, SEASON)["reason"] == "already compact"
    assert not [path for path in _legacy_paths(tmp_path) if path.is_file()]


def test_damage_after_the_index_switch_rebuilds_from_retained_legacy_shards(tmp_path):
    _seed(tmp_path)
    original = compact_curated._legacy_shards
    compact_curated._legacy_shards = lambda root, season: []
    try:
        compact(tmp_path, SEASON)
    finally:
        compact_curated._legacy_shards = original
    (tmp_path / f"data/curated/pitches/season={SEASON}/month=03.parquet").write_bytes(b"")

    result = compact(tmp_path, SEASON)

    assert result["changed"] == len(GAMES)
    rows = load_rows(tmp_path, "pitches", SEASON)
    assert sorted(row["game_id"] for row in rows) == sorted(game_id for game_id, _ in GAMES)


def test_damage_after_cleanup_refuses_to_claim_the_season_is_compact(tmp_path):
    _seed(tmp_path)
    compact(tmp_path, SEASON)
    assert not [path for path in _legacy_paths(tmp_path) if path.is_file()]
    (tmp_path / f"data/curated/pitches/season={SEASON}/month=03.parquet").write_bytes(b"")

    with pytest.raises(CompactionError):
        compact(tmp_path, SEASON)
