from pathlib import Path
import json
import tempfile

import xlsxwriter

from visualbaseball.zone_profile import build_zone_profiles


def test_zone_profile_builds_search_index_and_pitcher_payload():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "exports" / "visualbaseball_savant_2026_latest.xlsx"
        source.parent.mkdir(parents=True)
        columns = [
            "season", "parse_status", "pitcher_id", "pitcher_name", "batter_id", "batter_name", "pitch_type_kr",
            "px", "pz", "sz_top", "sz_bottom", "balls_before", "strikes_before",
            "is_swing", "is_contact", "is_in_play", "velocity_kmh", "is_pa_terminal", "pa_result", "x0",
        ]
        rows = [
            [2026, "ok", 99, "테스트투수", 88, "테스트타자", "직구", 0.1, 2.5, 3.5, 1.5, 0, 0, True, False, False, 150.0, False, "", 1.7],
            [2026, "ok", 99, "테스트투수", 88, "테스트타자", "직구", 0.2, 2.6, 3.5, 1.5, 0, 0, True, True, True, 148.0, True, "중안", 1.7],
        ]
        workbook = xlsxwriter.Workbook(source)
        sheet = workbook.add_worksheet("Pitches")
        sheet.write_row(0, 0, columns)
        for row_index, row in enumerate(rows, 1):
            sheet.write_row(row_index, 0, row)
        workbook.close()

        eligible, pitchers = build_zone_profiles(root, 2026, source)
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
        assert payload["records"][0][2] == "L"
        assert sum(record[6] for record in payload["records"]) == 2
        assert sum(record[8] for record in payload["records"]) == 1
        assert sum(record[15] for record in payload["records"]) == 1
        assert sum(record[16] for record in payload["records"]) == 1
        assert pitcher_payload["schema_version"] == 1
        assert sum(record[5] for record in pitcher_payload["records"]) == 2
