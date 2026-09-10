import pytest

from visualbaseball.curated import write_game
from visualbaseball.za_inputs import resolve_za_input


def _seed(root):
    write_game(root, {"season": 2026, "game_id": "g"}, [], [{"season": 2026, "game_id": "g", "pitch_id": "p"}])


def test_curated_is_the_only_za_input(tmp_path):
    _seed(tmp_path)
    selected = resolve_za_input(tmp_path, 2026)
    assert selected.mode == "curated"
    assert selected.path == tmp_path / "data/curated/pitches/season=2026"
    assert selected.events_path == tmp_path / "data/curated/events/season=2026"
    assert len(selected.sha256) == 64


def test_missing_curated_fails_closed(tmp_path):
    with pytest.raises(FileNotFoundError, match="canonical curated"):
        resolve_za_input(tmp_path, 2026)


def test_legacy_and_versioned_copies_are_rejected(tmp_path):
    _seed(tmp_path)
    with pytest.raises(ValueError, match="only accepts"):
        resolve_za_input(tmp_path, 2026, "legacy")
    with pytest.raises(ValueError, match="replaced"):
        resolve_za_input(tmp_path, 2026, "curated", "za-v1")
