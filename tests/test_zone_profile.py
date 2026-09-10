from pathlib import Path
import json
from visualbaseball.curated import write_game
from visualbaseball.zone_profile import build_zone_profiles


def test_zone_profile_builds_search_index_and_pitcher_payload():
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        rows = [
            {"season": 2026, "parse_status": "ok", "pitch_id": f"p{index}", "pitcher_id": 99,
             "pitcher_name": "테스트투수", "batter_id": 88, "batter_name": "테스트타자", "pitch_type_kr": "직구",
             "px": px, "pz": pz, "sz_top": 3.5, "sz_bottom": 1.5, "balls_before": 0, "strikes_before": 0,
             "is_swing": True, "is_contact": contact, "is_in_play": contact, "velocity_kmh": velocity,
             "is_pa_terminal": contact, "pa_result": "중안" if contact else "", "x0": 1.7, "y0": 50,
             "z0": 6, "vx0": 0, "vy0": -130, "vz0": 0, "ax": 0, "ay": 0, "az": 0}
            for index, (px, pz, contact, velocity) in enumerate(((0.1, 2.5, False, 150.0), (0.2, 2.6, True, 148.0)), 1)
        ]
        write_game(root, {"season": 2026, "game_id": "g"}, [], rows)

        eligible, pitchers = build_zone_profiles(root, 2026)
        index = json.loads((root / "web/data/zones/index.json").read_text(encoding="utf-8"))
        shard = json.loads((root / "web/data/zones/2026/batter/8.json").read_text(encoding="utf-8"))
        payload = shard["players"]["88"]
        pitcher_shard = json.loads((root / "web/data/zones/2026/pitcher/9.json").read_text(encoding="utf-8"))
        pitcher_payload = pitcher_shard["players"]["99"]

        assert (eligible, pitchers) == (2, 2)
        assert index["seasons"] == [2026]
        assert index["players"]["2026"]["batter"][0]["name"] == "테스트타자"
        assert index["players"]["2026"]["pitcher"][0]["name"] == "테스트투수"
        assert payload["schema_version"] == 2
        assert payload["strike_zone"] == {"left": -1.0, "right": 1.0, "bottom": 1.5, "top": 3.5}
        assert payload["home_plate"]["width_ft"] == 1.416667
        assert payload["records"][0][2] == "L"
        assert sum(record[6] for record in payload["records"]) == 2
        assert sum(record[8] for record in payload["records"]) == 1
        assert sum(record[15] for record in payload["records"]) == 1
        assert sum(record[16] for record in payload["records"]) == 1
        assert pitcher_payload["schema_version"] == 1
        assert sum(record[5] for record in pitcher_payload["records"]) == 2
