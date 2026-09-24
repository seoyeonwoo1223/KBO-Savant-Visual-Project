import csv
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("gate", Path(__file__).parents[1] / "scripts" / "check_zone_decision_outputs.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def _season(root, season, version="v2", za=1.5):
    base = root / "web/data/zone_awareness" / str(season)
    (base / "players").mkdir(parents=True)
    player = {"batter_id": "51234", "za_raw": za}
    (base / "leaderboard.json").write_text(json.dumps({"model_version": version, "players": [player]}), encoding="utf-8")
    (base / "players" / "51.json").write_text(json.dumps({"players": {"51234": {"summary": player}}}), encoding="utf-8")
    (root / "exports").mkdir(exist_ok=True)
    with (root / "exports" / f"zone_decision_players_{season}.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, ["batter_id", "za_raw"]); writer.writeheader(); writer.writerow({"batter_id": "51234", "za_raw": za})
    state = root / "data/metrics/_state" / str(season)
    state.mkdir(parents=True)
    (state / "zone_decision.json").write_text(json.dumps({"input_sha256": f"h{season}"}), encoding="utf-8")


def _root(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "metric_input_hash", lambda root, season, name: f"h{season}")
    (tmp_path / "web/data/zone_awareness").mkdir(parents=True)
    (tmp_path / "web/data/zone_awareness/index.json").write_text(json.dumps({"seasons": [2026, 2025, 2024]}), encoding="utf-8")
    for season in (2024, 2025, 2026):
        _season(tmp_path, season)
    return tmp_path


def test_consistent_seasons_pass(tmp_path, monkeypatch):
    assert gate.problems(_root(tmp_path, monkeypatch), model_version="v2") == []


def test_each_kind_of_disagreement_fails(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    board = root / "web/data/zone_awareness/2024/leaderboard.json"
    board.write_text(board.read_text().replace('"v2"', '"v1"'))                                  # older model
    (root / "web/data/zone_awareness/2025/players/51.json").unlink()                              # missing player file
    csv_path = root / "exports/zone_decision_players_2026.csv"
    csv_path.write_text(csv_path.read_text(encoding="utf-8-sig").replace("1.5", "1.6"), encoding="utf-8-sig")  # CSV drift
    monkeypatch.setattr(gate, "metric_input_hash", lambda r, season, name: "new" if season == 2026 else f"h{season}")  # stale state
    found = gate.problems(root, model_version="v2")
    assert any(line.startswith("2024: model_version") for line in found)
    assert any(line.startswith("2025: player file") for line in found)
    assert any(line.startswith("2026: CSV za_raw") for line in found)
    assert any(line.startswith("2026: build state") for line in found)
