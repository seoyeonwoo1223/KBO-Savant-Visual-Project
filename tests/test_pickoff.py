from visualbaseball.naver import NaverEnrichment, build_enrichment


def test_naver_pickoffs_are_retained_as_independent_events():
    payload = {"result": {"textRelayData": {
        "gameId": "20260901KTLG02026",
        "homeLineup": {"batter": []},
        "awayLineup": {"batter": []},
        "textRelays": [{
            "inn": 3,
            "homeOrAway": "0",
            "textOptions": [
                {"seqno": 10, "text": "1구 볼", "ptsPitchId": "p1", "pitchNum": 1,
                 "currentGameState": {"batter": "b1", "pitcher": "p9"}},
                {"seqno": 11, "text": "1루 견제", "ptsPitchId": None,
                 "currentGameState": {"batter": "b1", "pitcher": "p9"}},
                {"seqno": 12, "text": "1루 견제", "ptsPitchId": None,
                 "currentGameState": {"batter": "b1", "pitcher": "p9"}},
                {"seqno": 13, "text": "2구 스트라이크", "ptsPitchId": "p2", "pitchNum": 2,
                 "currentGameState": {"batter": "b1", "pitcher": "p9"}},
            ],
        }],
    }}}
    enrichment = build_enrichment("20260901KTLG0", [payload])
    assert len(enrichment.pickoff_events) == 2
    assert [event["pickoff_base"] for event in enrichment.pickoff_events] == [1, 1]
    assert all(event["pitcher_id"] == "p9" for event in enrichment.pickoff_events)
    assert enrichment.has_pickoff_coverage


def test_pickoff_out_and_runner_name_are_parsed():
    payload = {"result": {"textRelayData": {
        "gameId": "g2026",
        "textRelays": [{
            "inn": 7,
            "homeOrAway": "1",
            "textOptions": [{
                "seqno": 99,
                "text": "1루주자 홍길동 : 투수 견제로 아웃",
                "ptsPitchId": None,
                "currentGameState": {"batter": "b", "pitcher": "p"},
            }],
        }],
    }}}
    event = build_enrichment("g", [payload]).pickoff_events[0]
    assert event["pickoff_base"] == 1
    assert event["runner_name"] == "홍길동"
    assert event["is_pickoff_out"] is True


def test_legacy_naver_cache_is_recognized_as_missing_pickoff_coverage():
    legacy = NaverEnrichment.from_dict({
        "game_id": "g",
        "source_game_id": "ng",
        "source_urls": [],
        "starters": {},
        "coverage": "record_no_event",
        "pitch_events": [],
    })
    assert legacy.schema_version == 1
    assert not legacy.has_pickoff_coverage
