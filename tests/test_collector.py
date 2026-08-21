import json
from pathlib import Path
from unittest.mock import patch

import pyarrow.parquet as pq
import pytest

from visualbaseball.collector import process_payload
from visualbaseball.naver import NaverEnrichment, build_enrichment, pitch_key
from visualbaseball.parser import parse_game
from visualbaseball.state_machine import GameState
from visualbaseball.storage import Store
from visualbaseball.validation import validate_game
from visualbaseball.web_export import export_web_data
from visualbaseball.export_excel import export_latest


ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "data" / "raw" / "2026" / "20260328HTSK0.json"


def test_sample_game_and_idempotency(tmp_path):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8-sig"))
    ok, message, pitches = process_payload(tmp_path, payload)
    assert ok and message == "PASS" and pitches == 338
    first = pq.read_table(tmp_path / "data/processed/pitches.parquet").num_rows
    ok, message, pitches = process_payload(tmp_path, payload)
    assert ok and message == "PASS" and pitches == 338
    assert pq.read_table(tmp_path / "data/processed/pitches.parquet").num_rows == first
    rows = pq.read_table(tmp_path / "data/processed/pitches.parquet").to_pylist()
    assert len({row["pitch_id"] for row in rows}) == 338
    assert not any("spin" in key.lower() for row in rows for key in row)
    game_stadium = pq.read_table(tmp_path / "data/processed/games.parquet").to_pylist()[0]["stadium"]
    assert {row["stadium"] for row in rows} == {game_stadium}
    assert {row["stadium"] for row in pq.read_table(tmp_path / "data/processed/events.parquet").to_pylist()} == {game_stadium}


def test_y0_catcher_and_naver_wp_pb_fields_are_retained():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8-sig"))
    first_half, first_pa = payload["pbpData"][0], payload["pbpData"][0]["pas"][0]
    key = pitch_key(first_half["inning"], first_half["half"], first_pa["batterId"], first_pa["pitcherId"], 1)
    enrichment = NaverEnrichment(
        payload["gameData"]["gameId"], "naver-game", ["https://example.test/relay"],
        {key: [{"naver_pitch_id": "pitch-1", "is_wild_pitch": True, "is_passed_ball": False}]},
        {"home": {"id": "catcher-home", "name": "홈포수", "source": "naver_lineup"}},
    )
    _, _, pitches, _ = parse_game(payload, naver_enrichment=enrichment)
    first = pitches[0]
    assert first["y0"] == first_pa["pitches"][0]["y0"]
    assert (first["catcher_id"], first["catcher_name"], first["catcher_source"]) == ("catcher-home", "홈포수", "naver_lineup")
    assert (first["is_wild_pitch"], first["is_passed_ball"], first["naver_pitch_id"], first["naver_match_status"]) == (True, False, "pitch-1", "matched")


def test_naver_relay_event_is_assigned_to_the_previous_pitch():
    payload = {"result": {"textRelayData": {
        "gameId": "20260328KTLG02026",
        "homeLineup": {"batter": [{"pos": 2, "seqno": 1, "pcode": "10", "name": "홈포수"}]},
        "awayLineup": {"batter": [{"pos": 2, "seqno": 1, "pcode": "20", "name": "원정포수"}]},
        "textRelays": [{"inn": 1, "homeOrAway": "0", "textOptions": [
            {"text": "1구 볼", "ptsPitchId": "p1", "pitchNum": 1, "currentGameState": {"batter": "1", "pitcher": "2"}},
            {"text": "1루주자 홍길동 : 폭투로 2루까지 진루", "ptsPitchId": None},
            {"text": "2구 볼", "ptsPitchId": "p2", "pitchNum": 2, "currentGameState": {"batter": "1", "pitcher": "2"}},
            {"text": "2루주자 홍길동 : 포일로 3루까지 진루", "ptsPitchId": None},
            {"text": "3구 볼", "ptsPitchId": "p3", "pitchNum": 3, "currentGameState": {"batter": "1", "pitcher": "2"}},
        ]}],
    }}}
    enrichment = build_enrichment("20260328KTLG0", [payload])
    assert enrichment.starters["home"]["id"] == "10"
    assert enrichment.pitch_events[pitch_key(1, "top", "1", "2", 1)][0]["is_wild_pitch"] is True
    assert enrichment.pitch_events[pitch_key(1, "top", "1", "2", 2)][0]["is_passed_ball"] is True
    assert enrichment.pitch_events[pitch_key(1, "top", "1", "2", 3)][0]["is_passed_ball"] is False


def test_completed_status_is_not_written_when_processed_tables_fail(tmp_path):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8-sig"))
    with patch.object(Store, "replace_game", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            process_payload(tmp_path, payload)
    assert Store(tmp_path).manifest()["games"].get("20260328HTSK0") is None


def test_count_transitions_and_two_strike_foul():
    state = GameState(); state.apply_non_terminal_pitch("B"); assert state.balls == 1
    state.apply_non_terminal_pitch("S"); state.apply_non_terminal_pitch("F"); state.apply_non_terminal_pitch("F")
    assert state.strikes == 2


def test_runner_advances_multiple_outs_and_inning_reset():
    state = GameState(); state.set_bases({"b1": {"id": "a"}, "b2": {"id": "b"}}); state.outs = 1
    assert state.infer_runs({"b3": {"id": "a"}}, 3) == 0
    state.begin_half(2, "bottom")
    assert (state.outs, state.base_state_code, state.balls, state.strikes) == (0, 0, 0, 0)


def test_incremental_skip_logic(tmp_path):
    store = Store(tmp_path); raw = tmp_path / "data/raw/2026/old.json"; raw.parent.mkdir(parents=True); raw.write_text("{}")
    store.mark("old", "completed", raw, "PASS")
    assert store.should_fetch("old", "2000-01-01") is False


def test_incremental_skip_recovers_portable_raw_cache_from_legacy_absolute_path(tmp_path):
    store = Store(tmp_path)
    raw = tmp_path / "data/raw/2026/game.json"; raw.parent.mkdir(parents=True); raw.write_text("{}")
    store.mark("game", "completed", Path("C:/another-machine/data/raw/2026/game.json"), "PASS")
    assert store.should_fetch("game", "2026-07-26") is False


def test_official_linescore_overrides_conflicting_pbp_snapshot():
    payload = json.loads((ROOT / "data/raw/2026/20260527HTWO0.json").read_text(encoding="utf-8"))
    game, events, pitches, _ = parse_game(payload)
    assert validate_game(game, events, pitches) == (True, "PASS")
    assert (events[-1]["away_score_after"], events[-1]["home_score_after"]) == (9, 2)
    conflicts = [event for event in events if event["event_code"] == "SOURCE_SCORE_CONFLICT"]
    assert conflicts and all(event["parse_status"] == "unknown" for event in conflicts)


def test_web_export_writes_downloadable_game_and_movement_csv(tmp_path):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8-sig"))
    assert process_payload(tmp_path, payload)[0]
    output = export_web_data(tmp_path)
    assert "game_id" in (output / "games.csv").read_text(encoding="utf-8")
    assert "horizontal_movement_cm" in (output / "movement.csv").read_text(encoding="utf-8")
    assert json.loads((output / "summary.json").read_text(encoding="utf-8"))["pitches"] == 338


def test_season_export_uses_separate_storage_and_output_name(tmp_path):
    storage_root, output_root = tmp_path / "season", tmp_path / "output"
    payload = json.loads(FIXTURE.read_text(encoding="utf-8-sig"))
    assert process_payload(storage_root, payload, season=2025)[0]
    output = export_latest(output_root, 2025, storage_root)
    assert output.name == "visualbaseball_savant_2025_latest.xlsx"
    assert output.exists()
