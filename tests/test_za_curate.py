import json

import pytest

from visualbaseball.za_curate import curate, inventory, sha256
from visualbaseball.za_inputs import resolve_za_input


def test_inventory_is_read_only(tmp_path):
    source = tmp_path / "data/processed/pitches.parquet"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"legacy")
    events = source.with_name("events.parquet")
    events.write_bytes(b"events")
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    result = inventory(tmp_path, 2026)
    assert result["legacy_sha256"] == sha256(source)
    assert result["events_sha256"] == sha256(events)
    assert sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*")) == before


def test_curate_creates_only_versioned_copy_and_manifest(tmp_path):
    source = tmp_path / "data/processed/pitches.parquet"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"legacy stays unchanged")
    events = source.with_name("events.parquet")
    events.write_bytes(b"events stay unchanged")
    manifest_path = curate(tmp_path, 2026, "za-v1")
    manifest = json.loads(manifest_path.read_text())
    assert source.read_bytes() == b"legacy stays unchanged"
    assert manifest["seasons"]["2026"]["sha256"] == sha256(source)
    assert manifest["seasons"]["2026"]["events_sha256"] == sha256(events)
    selected = resolve_za_input(tmp_path, 2026, "curated", "za-v1")
    assert selected.path.read_bytes() == source.read_bytes()
    assert selected.events_path.read_bytes() == events.read_bytes()
    with pytest.raises(FileExistsError, match="immutable"):
        curate(tmp_path, 2026, "za-v1")
