"""Naver relay bunt fouls in 2019-2024 non-KIA-home games that have no TrackMan game, joined to VB and count-gated.

    PYTHONPATH=src python analysis/sbj_location/naver_non_tm_bunts.py games   # results/naver_non_tm_games_2019_2024.json
    PYTHONPATH=src python analysis/sbj_location/naver_non_tm_bunts.py fetch   # cache every inning (1 req/s)
    PYTHONPATH=src python analysis/sbj_location/naver_non_tm_bunts.py build   # results/naver_bunt_fouls_non_tm_2019_2024.csv + _summary.json

Target: curated games whose home code is not HT and that pa_flow_strict.load(season) does not map to a TrackMan game,
i.e. the games the TrackMan correction path (scripts/build_trackman_bunt_corrections.py) never sees
(naver_bunt_extension_design.md section 4 b). The join, the plate-appearance count gate and K1-K3 are those of
naver_kia_home_bunts.py. K4 is reported next to the same-season non-KIA sample and the KIA home value, not judged.
"""
from __future__ import annotations

import json, sys
from collections import defaultdict

from naver_kia_home_bunts import SEASONS, build, fetch
from naver_queue_verify import RESULTS, ROOT
from visualbaseball.curated import load_rows

sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "analysis/trajectory_audit")]

GAMES = RESULTS / "naver_non_tm_games_2019_2024.json"
COVERAGE = RESULTS / "naver_non_tm_fetch_2019_2024.json"
OUT_CSV = RESULTS / "naver_bunt_fouls_non_tm_2019_2024.csv"
OUT_SUMMARY = RESULTS / "naver_bunt_fouls_non_tm_2019_2024_summary.json"
KIA_SUMMARY = RESULTS / "naver_bunt_fouls_kia_home_2019_2024_summary.json"
SAMPLE_RECALL = RESULTS / "naver_non_kia_recall_2020_2023.json"
EXPECTED = {2019: 20, 2020: 3, 2021: 1, 2022: 17, 2023: 13, 2024: 13}


def find_games(seasons=SEASONS) -> dict[int, list[str]]:
    import pa_flow_strict as pf  # heavy import (pandas), only when the list is rebuilt
    out = {}
    for season in seasons:
        mapped = pf.load(season)[2]
        out[season] = sorted(r["game_id"] for r in load_rows(ROOT, "games", season, columns=["game_id"])
                             if r["game_id"][10:12] != "HT" and r["game_id"] not in mapped)
    return out


def write_games() -> dict[int, list[str]]:
    by_season = find_games()
    GAMES.write_text(json.dumps({"definition": "curated games with home code != HT that pa_flow_strict.load(season) does not map to a TrackMan game",
                                 "counts": {str(s): len(g) for s, g in by_season.items()},
                                 "expected_counts": {str(s): n for s, n in EXPECTED.items()},
                                 "games": {str(s): g for s, g in by_season.items()}}, ensure_ascii=False, indent=1), encoding="utf-8")
    return by_season


def read_games() -> list[str]:
    """The fixed list. It is not recomputed by fetch/build so a rerun uses the same games."""
    return [g for gs in json.loads(GAMES.read_text(encoding="utf-8"))["games"].values() for g in gs]


def k4_reference(summary: dict) -> None:
    kia = json.loads(KIA_SUMMARY.read_text(encoding="utf-8"))["seasons"] if KIA_SUMMARY.exists() else {}
    sample = json.loads(SAMPLE_RECALL.read_text(encoding="utf-8"))["seasons"] if SAMPLE_RECALL.exists() else {}
    for season, body in summary["seasons"].items():
        body["K4_reference"] = {
            "non_tm_W_per_game": body["K4_W_per_game"],
            "kia_home_W_per_game": kia.get(season, {}).get("K4_W_per_game"),
            "non_kia_sample_W_per_game": round(sample[season]["stats"]["naver_W"] / sample[season]["games"], 3) if season in sample else None,
            "note": "reported only; not a pass/fail gate for this table"}
        body.pop("K4_pass", None)


def main() -> None:
    mode = sys.argv[1]
    if mode == "games":
        by_season = write_games()
        print({s: len(g) for s, g in by_season.items()}, "expected", EXPECTED)
    elif mode == "fetch":
        fetch(read_games(), COVERAGE)
    else:
        summary = build(SEASONS, read_games(), OUT_CSV, OUT_SUMMARY, games_definition=(
            "curated games, home code not HT, not mapped to a TrackMan game by pa_flow_strict.load (list: " + GAMES.name + ")"))
        k4_reference(summary)
        OUT_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
