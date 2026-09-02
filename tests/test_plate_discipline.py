from __future__ import annotations

import json

import pyarrow as pa
import pyarrow.parquet as pq

from visualbaseball.plate_discipline import build_plate_discipline


def test_plate_discipline_exports_base_rates_and_metadata(tmp_path):
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    rows = []
    zones = [(0.0, 0.0), (0.8, 0.8), (1.15, 1.15), (1.6, 1.6), (2.2, 2.2)]
    for batter in range(10):
        for index in range(400):
            x, z = zones[index % len(zones)]
            zone_index = index % len(zones)
            within_zone = index // len(zones)
            thresholds = (25 + batter * 5, 20 + batter * 4, 15 + batter * 3, 10 + batter * 2, 5 + batter)
            swing = within_zone < thresholds[zone_index]
            rows.append({
                "season": 2026,
                "game_date": "2026-04-01",
                "game_id": "g",
                "pa_id": f"p-{batter}-{index // 4}",
                "pitch_id": f"x-{batter}-{index}",
                "batter_id": str(batter),
                "batter_name": f"타자{batter}",
                "batter_stance": "R",
                "pitcher_id": "p",
                "pitch_type": "4-Seam Fastball",
                "balls_before": 0,
                "strikes_before": 0,
                "x_relative": x,
                "z_relative": z,
                "decision_type": "Swing" if swing else "Take",
                "is_contact": swing and index % 3 != 0,
                "decision_run": (0.01 if swing else -0.005) * (batter + 1),
            })
    pq.write_table(pa.Table.from_pylist(rows), processed / "decision_pitches.parquet")

    pitches, batters = build_plate_discipline(tmp_path)

    assert pitches == 4000
    assert batters == 10
    player_rows = pq.read_table(processed / "plate_discipline_batters.parquet").to_pylist()
    assert all(row["qualified_300"] for row in player_rows)
    assert all(row["heart_pitches"] == 80 for row in player_rows)
    assert all(row["cluster_id"] >= 1 for row in player_rows)
    assert all(row["simple_seager"] is not None for row in player_rows)
    assert all(row["zone_awareness_plus"] is not None for row in player_rows)
    assert all(row["pure_cluster_id"] is not None for row in player_rows)
    assert all(
        row["seager_a_zone_swings"] + row["seager_b_out_swings"]
        + row["seager_c_zone_takes"] + row["seager_d_out_takes"] == row["pitches_seen"]
        for row in player_rows
    )
    metadata = json.loads((processed / "plate_discipline_research.json").read_text())
    assert metadata["qualified_batters"] == 10
    assert metadata["regressions"][0]["x"] == "chase_swing_pct"
    assert metadata["pure_zone_awareness_beta"]["contact_or_in_play_used"] is False
    assert (tmp_path / "exports" / "plate_discipline_research_2026.csv").exists()
