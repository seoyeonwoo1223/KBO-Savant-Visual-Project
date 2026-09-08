import hashlib
import json

import pytest

from visualbaseball.za_inputs import resolve_za_input


def test_legacy_is_the_default(tmp_path):
    selected = resolve_za_input(tmp_path, 2026)
    assert selected.mode == "legacy"
    assert selected.path == tmp_path / "data/processed/pitches.parquet"


def test_legacy_2026_uses_separate_storage_root(tmp_path):
    storage_root = tmp_path / "season"
    selected = resolve_za_input(tmp_path, 2026, storage_root=storage_root)
    assert selected.path == storage_root / "data/processed/pitches.parquet"


def test_curated_requires_a_valid_manifest_and_checksum(tmp_path):
    version_root = tmp_path / "data/curated/zone_awareness/za-v1"
    version_root.mkdir(parents=True)
    source = version_root / "pitches.parquet"
    source.write_bytes(b"curated")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    (version_root / "manifest.json").write_text(json.dumps({
        "schema_version": 1, "version": "za-v1",
        "seasons": {"2026": {"path": "pitches.parquet", "sha256": digest}},
    }))
    selected = resolve_za_input(tmp_path, 2026, "curated", "za-v1")
    assert selected.path == source
    assert selected.sha256 == digest

    source.write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum mismatch"):
        resolve_za_input(tmp_path, 2026, "curated", "za-v1")


def test_curated_never_falls_back_to_legacy(tmp_path):
    (tmp_path / "data/processed").mkdir(parents=True)
    (tmp_path / "data/processed/pitches.parquet").touch()
    with pytest.raises(FileNotFoundError, match="manifest is required"):
        resolve_za_input(tmp_path, 2026, "curated", "missing")


def test_curated_version_cannot_escape(tmp_path):
    with pytest.raises(ValueError, match="path-safe"):
        resolve_za_input(tmp_path, 2026, "curated", "../escape")
