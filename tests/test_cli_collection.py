"""Network collection path of cli.main(), driven with in-memory fakes."""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from visualbaseball import cli


def _schedule(count: int) -> dict:
    return {"2026-04-01": [{"gameId": f"20260401G{index:03d}", "status": "final"} for index in range(count)]}


class FakeClient:
    schedule: dict = {}

    def get_json(self, path: str, referer: str | None = None) -> dict:
        if path.startswith("/api/schedule/season"):
            return {"schedule": self.schedule}
        game_id = path.split("id=")[1]
        return {"gameId": game_id, "pbpData": [{"inning": 9}]}


class FakeStore:
    def __init__(self, storage_root, root) -> None:
        self.batches: list[list[str]] = []
        self.marked: list[str] = []
        FakeStore.last = self

    def replace_games(self, games, events, pitches) -> int:
        self.batches.append([game["game_id"] for game in games])
        return len(games)

    def mark(self, game_id, status, raw_path=None, message="") -> None:
        self.marked.append(game_id)


@pytest.fixture
def collection(monkeypatch, tmp_path):
    calls = {"exports": [], "fetched": []}

    def prepare_game(payload, schedule_game, season, naver):
        calls["fetched"].append(payload["gameId"])
        game = {"game_id": payload["gameId"]}
        return SimpleNamespace(game=game, events=[], pitches=[{"pitch_id": payload["gameId"], "y0": 50.0}], message="ok")

    monkeypatch.setattr(cli, "VisualBaseballClient", FakeClient)
    monkeypatch.setattr(cli, "Store", FakeStore)
    monkeypatch.setattr(cli, "select_target_games",
                        lambda schedule, store, season, mode, game_id=None: [game for games in schedule.values() for game in games])
    monkeypatch.setattr(cli, "_load_naver", lambda *args: object())
    monkeypatch.setattr(cli, "prepare_game", prepare_game)
    monkeypatch.setattr(cli, "cache_payload", lambda store, season, payload, prepared: tmp_path / f"{payload['gameId']}.json")
    monkeypatch.setattr(cli, "_exports", lambda root, season, storage_root: calls["exports"].append(season))
    monkeypatch.setattr(sys, "argv", ["cli", "--root", str(tmp_path)])
    return calls, tmp_path


def test_collection_stores_games_in_batches_of_25_then_exports(collection, monkeypatch, capsys):
    calls, _ = collection
    FakeClient.schedule = _schedule(30)
    monkeypatch.setattr(sys, "argv", [*sys.argv, "--refresh-workers", "3"])
    cli.main()
    store = FakeStore.last
    assert [len(batch) for batch in store.batches] == [25, 5]
    assert [game for batch in store.batches for game in batch] == [f"20260401G{index:03d}" for index in range(30)]
    assert store.marked == [game for batch in store.batches for game in batch]
    assert calls["exports"] == [2026]
    assert "reconciled 30 games; 30 curated shards changed" in capsys.readouterr().out


def test_sample_with_changed_pitch_inputs_triggers_auto_reconcile(collection, monkeypatch, capsys):
    calls, root = collection
    FakeClient.schedule = _schedule(3)
    for index in range(2):
        manifest = cli.source_manifest_path(root, 2026, f"20260401G{index:03d}")
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps({"pitch_sha256": "old", "schema_sha256": cli.schema_sha256(), "observed_y0": [50.0]}), encoding="utf-8")
    sampled = FakeClient.schedule["2026-04-01"][:2]
    monkeypatch.setattr(cli, "select_target_games",
                        lambda schedule, store, season, mode, game_id=None: sampled if mode == "sample" else FakeClient.schedule["2026-04-01"])
    monkeypatch.setattr(sys, "argv", [*sys.argv, "--collection-mode", "sample", "--auto-reconcile"])
    cli.main()
    assert calls["fetched"] == ["20260401G000", "20260401G001", "20260401G002"]
    assert FakeStore.last.batches == [["20260401G000", "20260401G001", "20260401G002"]]
    assert "sample triggered automatic reconcile of 1 games" in capsys.readouterr().out
