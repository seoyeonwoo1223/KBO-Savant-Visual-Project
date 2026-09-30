from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis/sbj_location"))

from bunt_attempts import match, observed


def test_bunt_pitch_and_result_attach_only_to_the_batted_pitch():
    def pitch(seq, number, code, text, pid):
        return {"seqno": seq, "pitchNum": number, "pitchResult": code,
                "text": text, "ptsPitchId": pid, "speed": 140,
                "currentGameState": {"pitcher": "1", "batter": "2", "ball": "0", "strike": "1"}}
    relay = {"textRelays": [{"inn": 1, "homeOrAway": "0", "no": 1,
              "textOptions": [pitch(1, 1, "W", "1구 번트파울", "p1"),
                              pitch(2, 2, "H", "2구 타격", "p2"),
                              {"seqno": 3, "text": "희생번트 아웃"}]}]}
    rows = observed(relay)
    assert [(r["naver_pitch_id"], r["naver_code"], r["naver_phrase"]) for r in rows] == [
        ("p1", "W", "번트파울"), ("p2", "H", "희생번트아웃")]
    relay["textRelays"][0]["textOptions"][0]["ptsPitchId"] = -1
    assert observed(relay)[0]["naver_phrase"] == "번트파울"
    assert observed(relay)[0]["naver_pitch_id"] == ""
    relay["textRelays"][0]["textOptions"] = [pitch(1, 1, "W", "1구 번트파울", "p1"),
                                               {"seqno": 2, "text": "포수 쓰리번트 아웃"}]
    assert observed(relay)[0]["naver_phrase"] == "번트파울 / 쓰리번트아웃"


def test_id_priority_and_ambiguous_context():
    naver = {"game_id": "g", "inning": 1, "half": "top", "pitcher_id": "1",
             "batter_id": "2", "pitch_num": 1, "speed": 140, "naver_pitch_id": "n"}
    a = {"pitch_id": "a", "velocity_kmh": 140}
    b = {"pitch_id": "b", "velocity_kmh": 141}
    context = {("g", 1, "top", "1", "2", 1): [a, b]}
    assert match(naver, {("g", "n"): [a]}, context) == ("matched_id", a)
    assert match(naver, {}, context) == ("ambiguous", None)
