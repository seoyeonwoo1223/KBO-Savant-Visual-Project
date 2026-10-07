from types import SimpleNamespace

from visualbaseball.leaderboard_dh import confirmed_position, verify_inning, load_verifications, _fingerprint


def vb(pa_id, seq, **changes):
    return dict(game_id="20260401KTHH0", inning=8, inning_half="top", batter_id="78548",
                batter_name="장성우", batter_position="지포", is_pa_terminal=True,
                pa_id=pa_id, event_seq=seq, **changes)


def relay(*positions):
    options = [{"type": 0, "seqno": 0, "batterRecord": {"pcode": "78548", "pos": 0, "name": "장성우"}}]
    for index, position in enumerate(positions):
        options += [{"type": 8, "seqno": index * 3 + 1, "batterRecord": {
            "pcode": "78548", "pos": position, "posName": "지명타자" if position == 0 else "포수", "name": "장성우"}},
            {"type": 1, "seqno": index * 3 + 2, "ptsPitchId": f"pitch{index}"},
            {"type": 13, "seqno": index * 3 + 3}]
    return {"result": {"textRelayData": {"gameId": "20260401KTHH02026", "textRelays": [
        {"inn": 8, "homeOrAway": "0", "textOptions": options}]}}}


def test_repeated_batter_and_role_change_use_pa_order_not_final_lineup():
    records = verify_inning([vb("b", 2), vb("a", 1)], relay(0, 2), "20260401KTHH0", 2026, 8)
    assert [(r["pa_id"], r["position"]) for r in records] == [("a", "DH"), ("b", "C")]
    assert confirmed_position(SimpleNamespace(**vb("a", 1)), records[0]) == "DH"
    assert confirmed_position(SimpleNamespace(**{**vb("a", 1), "batter_name": "다른 선수"}), records[0]) is None


def test_missing_pa_or_pinch_hitter_position_remain_unknown():
    records = verify_inning([vb("a", 1), vb("b", 2)], relay(0), "20260401KTHH0", 2026, 8)
    assert all(r["status"] == "pa_count_mismatch" and r["position"] is None for r in records)
    assert verify_inning([vb("a", 1)], relay(10), "20260401KTHH0", 2026, 8)[0]["status"] == "position_unavailable"


def test_repeated_announcement_before_first_pitch_is_one_pa():
    payload = relay(0)
    options = payload["result"]["textRelayData"]["textRelays"][0]["textOptions"]
    options += [{**options[1], "seqno": -2}, {"type": 2, "seqno": -1, "text": "수비 교체"}]
    records = verify_inning([vb("a", 1)], payload, "20260401KTHH0", 2026, 8)
    assert records[0]["position"] == "DH" and records[0]["naver_pa_count"] == 1


def test_verifications_are_invalidated_when_vb_inning_changes(tmp_path):
    import json
    import pytest
    rows = [vb("a", 1)]
    records = verify_inning(rows, relay(0), "20260401KTHH0", 2026, 8)
    source = tmp_path / "data/leaderboards/source/2026_dh.json"
    source.parent.mkdir(parents=True)
    payload = {"season": 2026, "scope": "vb_mixed_dh", "innings": {
        "20260401KTHH0:8": {"input_sha256": _fingerprint(rows), "records": records}}}
    source.write_text(json.dumps(payload))
    assert load_verifications(tmp_path, 2026, rows)["a"]["position"] == "DH"
    assert load_verifications(tmp_path, 2026, rows + [vb("b", 2)]) == {}
    payload["season"] = 2025
    source.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        load_verifications(tmp_path, 2026, rows)


def test_leaderboard_only_build_is_offline_and_rejects_other_seasons(tmp_path, monkeypatch):
    import pytest
    from visualbaseball import cli
    calls = []
    monkeypatch.setattr(cli, "_build_metric", lambda root, season, name, build: (calls.append(name), build()))
    monkeypatch.setattr(cli, "build_vb_leaderboard", lambda root, season: calls.append(season))
    parser = cli._arguments()
    cli._build_only(parser, parser.parse_args(["--only", "leaderboards"]), tmp_path)
    assert calls == ["leaderboards", 2026]
    with pytest.raises(SystemExit):
        cli._build_only(parser, parser.parse_args(["--only", "leaderboards", "--season", "2025"]), tmp_path)


def test_refresh_reuses_verified_inputs_and_retries_unknown(tmp_path, monkeypatch):
    from visualbaseball import leaderboard_dh as dh
    rows = [vb("a", 1)]
    calls = []
    replies = [relay(10), relay(0), relay(0, 2)]
    monkeypatch.setattr(dh, "load_rows", lambda *args, **kwargs: rows)

    class Client:
        base_url = "https://api-gw.sports.naver.com"

        def get_json(self, path):
            calls.append(path)
            return replies.pop(0)

    monkeypatch.setattr(dh, "NaverSportsClient", Client)
    dh.refresh_dh(tmp_path)
    assert load_verifications(tmp_path, 2026, rows)["a"]["status"] == "position_unavailable"
    dh.refresh_dh(tmp_path)
    assert load_verifications(tmp_path, 2026, rows)["a"]["position"] == "DH"
    source = tmp_path / "data/leaderboards/source/2026_dh.json"
    before = source.read_bytes()
    dh.refresh_dh(tmp_path)
    assert source.read_bytes() == before and len(calls) == 2
    rows.append(vb("b", 2))
    assert load_verifications(tmp_path, 2026, rows) == {}
    dh.refresh_dh(tmp_path)
    assert len(calls) == 3 and load_verifications(tmp_path, 2026, rows)["b"]["position"] == "C"
