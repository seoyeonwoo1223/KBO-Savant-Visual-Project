import json
from pathlib import Path

from visualbaseball.build_curated import build_curated
from visualbaseball.curated import load_table


ROOT = Path(__file__).parents[1]


def test_raw_build_creates_game_shards_and_provenance(tmp_path):
    raw = tmp_path / "storage/data/raw/2026/20260328HTSK0.json"
    raw.parent.mkdir(parents=True)
    raw.write_bytes((ROOT / "data/raw/2026/20260328HTSK0.json").read_bytes())
    result = build_curated(tmp_path, 2026, storage_root=tmp_path / "storage", validate=True)
    assert result["games"] == result["changed"] == 1
    assert result["pitches"] == 338
    assert load_table(tmp_path, "pitches", 2026).num_rows == 338
    manifest = json.loads((tmp_path / "data/curated/sources/season=2026/20260328HTSK0.json").read_text(encoding="utf-8"))
    assert manifest["raw_pitch_count"] == manifest["curated_pitch_count"] == 338
    assert len(manifest["raw_sha256"]) == len(manifest["pitch_sha256"]) == len(manifest["schema_sha256"]) == 64


def test_unchanged_build_is_a_noop(tmp_path):
    raw = tmp_path / "data/raw/2026/20260328HTSK0.json"
    raw.parent.mkdir(parents=True)
    raw.write_bytes((ROOT / "data/raw/2026/20260328HTSK0.json").read_bytes())
    assert build_curated(tmp_path, 2026)["changed"] == 1
    shard = tmp_path / "data/curated/pitches/season=2026/20260328HTSK0.parquet"
    before = shard.read_bytes()
    assert build_curated(tmp_path, 2026)["changed"] == 0
    assert shard.read_bytes() == before
