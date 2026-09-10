import json
from datetime import date
from pathlib import Path

from visualbaseball.cli import select_target_games
from visualbaseball.collector import process_payload
from visualbaseball.curated import load_table, normalize_trajectory
from visualbaseball.parser import parse_game
from visualbaseball.storage import Store


ROOT = Path(__file__).parents[1]


def test_known_55ft_pitch_normalizes_to_requested_50ft_example():
    payload = json.loads((ROOT / "data/raw/2026/20260718WOHH0.json").read_text(encoding="utf-8-sig"))
    pitch = next(row for row in parse_game(payload)[2] if row["pitcher_id"] == "68341")
    row = normalize_trajectory(pitch)
    assert abs(row["z0"] * 30.48 - 179.923) < .001
    assert abs(row["release_z_50"] - 171.9006) < .001
    assert row["release_z_55"] == row["z0"] * 30.48
    assert row["release_height_cm"] == 171.9


def test_raw_change_is_audited_before_replacement_and_raw_only_change_skips_shard(tmp_path):
    source = json.loads((ROOT / "data/raw/2026/20260328HTSK0.json").read_text(encoding="utf-8-sig"))
    assert process_payload(tmp_path, source)[0]
    shard = tmp_path / "data/curated/pitches/season=2026/20260328HTSK0.parquet"
    before = shard.read_bytes()
    changed = json.loads(json.dumps(source))
    changed["providerDecorativeField"] = "new"
    assert process_payload(tmp_path, changed)[0]
    assert shard.read_bytes() == before
    audit = (tmp_path / "data/curated/audit/season=2026/20260328HTSK0.jsonl").read_text(encoding="utf-8")
    assert "providerDecorativeField" in audit


def test_loader_prunes_columns_and_players(tmp_path):
    payload = json.loads((ROOT / "data/raw/2026/20260328HTSK0.json").read_text(encoding="utf-8-sig"))
    process_payload(tmp_path, payload)
    pitcher_id = load_table(tmp_path, "pitches", 2026, ["pitcher_id"]).column("pitcher_id")[0].as_py()
    player = load_table(tmp_path, "pitches", 2026, ["pitch_id", "pitcher_id"], player_id=pitcher_id)
    assert player.column_names == ["pitch_id", "pitcher_id"]
    assert player.num_rows and set(player.column("pitcher_id").to_pylist()) == {pitcher_id}


def test_collection_modes_recent_sample_reconcile(tmp_path):
    schedule = {f"2026-0{month}-{day:02d}": [{"gameId": f"g{month}{day}", "status": "final"}]
                for month in range(1, 4) for day in range(1, 11)}
    store = Store(tmp_path)
    assert len(select_target_games(schedule, store, 2026, "sample", today=date(2026, 9, 10))) == 8
    assert len(select_target_games(schedule, store, 2026, "reconcile", today=date(2026, 9, 10))) == 30
    schedule["2026-09-10"] = [{"gameId": "live", "status": "playing"}]
    schedule["2026-09-11"] = [{"gameId": "future", "status": "scheduled"}]
    recent_ids = {game["gameId"] for game in select_target_games(schedule, store, 2026, "recent", today=date(2026, 9, 10))}
    assert "live" in recent_ids and "future" not in recent_ids
