from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

RAW_DIR = Path("data/raw/2026")
PITCH_DIR = Path("data/curated/pitches/season=2026")
OUT_DIR = Path("data/experimental/pickoff/2026")


def occupied(value: object) -> bool:
    return value not in (None, "", 0, "0", False, {}, [])


def has_runner(code: object, r1: object, r2: object, r3: object) -> bool:
    if code not in (None, 0, "0", ""):
        try:
            if int(code) != 0:
                return True
        except (TypeError, ValueError):
            pass
    return any(value not in (None, "", 0, "0") for value in (r1, r2, r3))


def main() -> None:
    events = json.loads((OUT_DIR / "disengagement_events.json").read_text(encoding="utf-8"))
    crawl = json.loads((OUT_DIR / "disengagement_summary.json").read_text(encoding="utf-8"))
    crawl_game_ids = {str(row["game_id"]) for row in crawl.get("per_game", [])}

    game_meta: dict[str, dict[str, str]] = {}
    for path in RAW_DIR.glob("*.json"):
        if path.stem not in crawl_game_ids:
            continue
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        game_data = payload.get("gameData") or {}
        game_id = str(game_data.get("gameId") or path.stem)
        game_meta[game_id] = {
            "away": str((game_data.get("away") or {}).get("team") or ""),
            "home": str((game_data.get("home") or {}).get("team") or ""),
        }

    defensive_runner_pitches: Counter[str] = Counter()
    offensive_runner_pitches: Counter[str] = Counter()
    games_with_pitch_data: set[str] = set()
    missing_meta: set[str] = set()
    pitch_rows_scanned = 0
    runner_pitch_rows = 0

    columns = [
        "inning_half",
        "base_state_code_before",
        "runner_1b_id_before",
        "runner_2b_id_before",
        "runner_3b_id_before",
    ]

    for path in sorted(PITCH_DIR.glob("*.parquet")):
        game_id = path.stem
        if game_id not in crawl_game_ids:
            continue
        meta = game_meta.get(game_id)
        if not meta or not meta["away"] or not meta["home"]:
            missing_meta.add(game_id)
            continue

        table = pq.read_table(path, columns=columns)
        data = table.to_pydict()
        games_with_pitch_data.add(game_id)
        pitch_rows_scanned += table.num_rows

        for index in range(table.num_rows):
            if not has_runner(
                data["base_state_code_before"][index],
                data["runner_1b_id_before"][index],
                data["runner_2b_id_before"][index],
                data["runner_3b_id_before"][index],
            ):
                continue
            half = str(data["inning_half"][index] or "").lower()
            if half == "top":
                offense, defense = meta["away"], meta["home"]
            elif half == "bottom":
                offense, defense = meta["home"], meta["away"]
            else:
                raise RuntimeError(f"unknown inning_half={half!r} game={game_id}")
            offensive_runner_pitches[offense] += 1
            defensive_runner_pitches[defense] += 1
            runner_pitch_rows += 1

    covered_games = crawl_game_ids & games_with_pitch_data
    uncovered_games = crawl_game_ids - covered_games

    covered_events = [event for event in events if str(event.get("game_id") or "") in covered_games]
    uncovered_events = [event for event in events if str(event.get("game_id") or "") in uncovered_games]

    runner_events: list[dict] = []
    empty_events: list[dict] = []
    for event in covered_events:
        state = event.get("current_game_state") or {}
        target = runner_events if any(occupied(state.get(base)) for base in ("base1", "base2", "base3")) else empty_events
        target.append(event)

    made = Counter(str(event.get("pitching_team") or "") for event in runner_events)
    received = Counter(str(event.get("batting_team") or "") for event in runner_events)

    teams = sorted(
        (set(made) | set(received) | set(defensive_runner_pitches) | set(offensive_runner_pitches)) - {""}
    )
    rows: list[dict] = []
    for team in teams:
        disengagements_made = int(made[team])
        disengagements_received = int(received[team])
        defensive_rp = int(defensive_runner_pitches[team])
        offensive_rp = int(offensive_runner_pitches[team])
        rows.append(
            {
                "team": team,
                "disengagements_made": disengagements_made,
                "defensive_runner_pitches": defensive_rp,
                "disengagements_per_100_runner_pitches": round(disengagements_made * 100 / defensive_rp, 3)
                if defensive_rp
                else None,
                "disengagements_received": disengagements_received,
                "offensive_runner_pitches": offensive_rp,
                "received_disengagements_per_100_runner_pitches": round(
                    disengagements_received * 100 / offensive_rp, 3
                )
                if offensive_rp
                else None,
            }
        )

    made_sorted = sorted(rows, key=lambda row: (-(row["disengagements_per_100_runner_pitches"] or -1), row["team"]))
    received_sorted = sorted(
        rows,
        key=lambda row: (-(row["received_disengagements_per_100_runner_pitches"] or -1), row["team"]),
    )
    made_rank = {row["team"]: rank for rank, row in enumerate(made_sorted, 1)}
    received_rank = {row["team"]: rank for rank, row in enumerate(received_sorted, 1)}
    for row in rows:
        row["disengagement_rate_rank"] = made_rank[row["team"]]
        row["received_disengagement_rate_rank"] = received_rank[row["team"]]
    rows.sort(key=lambda row: row["disengagement_rate_rank"])

    total_made = sum(made.values())
    total_received = sum(received.values())
    total_defensive_rp = sum(defensive_runner_pitches.values())
    total_offensive_rp = sum(offensive_runner_pitches.values())
    assert total_made == total_received
    assert total_defensive_rp == total_offensive_rp == runner_pitch_rows

    result = {
        "season": 2026,
        "metric": "Disengagements / 100 Runner Pitches",
        "definition": "Naver relay '투수판 이탈' events with at least one runner on base / curated pitches with at least one runner immediately before the pitch * 100",
        "coverage_rule": "Numerator and denominator are restricted to the identical set of games that have both Naver disengagement crawl coverage and curated pitch data.",
        "source": {
            "numerator": "Naver Sports public textRelayData",
            "denominator": "data/curated/pitches/season=2026/*.parquet",
        },
        "coverage": {
            "crawl_games": len(crawl_game_ids),
            "metric_games": len(covered_games),
            "games_excluded_missing_curated_pitch_data": len(uncovered_games),
            "excluded_game_ids": sorted(uncovered_games),
            "missing_game_metadata": sorted(missing_meta),
            "pitch_rows_scanned": pitch_rows_scanned,
        },
        "league_totals": {
            "source_disengagement_events_all_688_games": len(events),
            "covered_disengagement_events_all_base_states": len(covered_events),
            "covered_runner_present_disengagement_events": len(runner_events),
            "covered_bases_empty_disengagement_events_excluded": len(empty_events),
            "disengagement_events_excluded_for_missing_denominator_coverage": len(uncovered_events),
            "runner_pitches": runner_pitch_rows,
            "disengagements_per_100_runner_pitches": round(total_made * 100 / total_defensive_rp, 3)
            if total_defensive_rp
            else None,
        },
        "invariants": {
            "made_equals_received": total_made == total_received,
            "defensive_runner_pitches_equal_offensive": total_defensive_rp == total_offensive_rp,
            "numerator_and_denominator_game_sets_match": True,
        },
        "teams": rows,
    }

    json_path = OUT_DIR / "disengagement_rate_team_summary.json"
    csv_path = OUT_DIR / "disengagement_rate_team_summary.csv"
    parquet_path = OUT_DIR / "disengagement_rate_team_summary.parquet"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    fields = [
        "disengagement_rate_rank",
        "team",
        "disengagements_made",
        "defensive_runner_pitches",
        "disengagements_per_100_runner_pitches",
        "disengagements_received",
        "offensive_runner_pitches",
        "received_disengagements_per_100_runner_pitches",
        "received_disengagement_rate_rank",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    pq.write_table(pa.Table.from_pylist(rows), parquet_path)

    readme_path = OUT_DIR / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    marker = "## Disengagements / 100 Runner Pitches"
    section = f"""
## Disengagements / 100 Runner Pitches

Team-level outputs:

- `disengagement_rate_team_summary.json`
- `disengagement_rate_team_summary.csv`
- `disengagement_rate_team_summary.parquet`

Definition: runner-present `투수판 이탈` events / runner-pitches × 100.

- Numerator and denominator are restricted to the same {len(covered_games)} games with curated pitch data.
- {len(uncovered_games)} crawled games without a curated pitch denominator are excluded from both sides of the rate.
- Numerator excludes `투수판 이탈` records whose Naver `currentGameState` has all bases empty.
- Denominator is a curated pitch with `base_state_code_before != 0` or any runner-before id present.
- Defensive rate is attributed to the pitching team; received rate is attributed to the batting team.
- Keep the label `Disengagements`, not literal `Pickoff Throws`, because a disengagement can include a step-off without an actual throw.
""".strip()
    if marker in readme:
        readme = readme.split(marker)[0].rstrip()
    readme_path.write_text(readme.rstrip() + "\n\n" + section + "\n", encoding="utf-8")

    print("COVERAGE", json.dumps(result["coverage"], ensure_ascii=False))
    print("LEAGUE_TOTALS", json.dumps(result["league_totals"], ensure_ascii=False))
    for row in rows:
        print("TEAM", json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
