"""Add Naver-relay bunt fouls (2025-2026) to data/corrections/vb_bunt_foul_corrections.json.

    PYTHONPATH=src python scripts/build_naver_bunt_corrections.py <bunt_attempts_2025_2026.csv> [seasons...]

Input is the per-pitch Naver bunt table from PR #32 (analysis/sbj_location/results/bunt_attempts_2025_2026.csv,
commit 1979b77e): Naver relay code `W` (번트파울) joined to a VB pitch. A row becomes a correction only when
Naver says `W`, VB recorded `B`, and the join is `matched_id` or `matched_context` (unmatched/ambiguous rows are
never used). Batter, pitcher and displayed velocity come from curated so the parser guard can check the raw
pitch. Unlike the TrackMan table, a two-strike bunt foul that ends the plate appearance is included.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from visualbaseball.curated import load_rows

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_trackman_bunt_corrections as tm  # noqa: E402

ROOT = tm.ROOT
RULE = "Naver relay pitchResult W (번트파울) joined to a VB pitch recorded as B (matched_id or matched_context)."


def main() -> None:
    source, seasons = Path(sys.argv[1]), [s for s in sys.argv[2:]] or ["2025", "2026"]
    with source.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    table = tm.json.loads(tm.OUT.read_text(encoding="utf-8"))
    table.update(tm.HEADER)
    for season in seasons:
        picked = [r for r in rows if r["season"] == season and r["naver_code"] == "W" and r["vb_call"] == "B"
                  and r["match_status"] in {"matched_id", "matched_context"}]
        curated = {r["pitch_id"]: r for r in load_rows(ROOT, "pitches", int(season), columns=[
            "pitch_id", "batter_id", "pitcher_id", "velocity_kmh", "pitch_call_code", "is_pa_terminal"])}
        entries, missing = [], 0
        for r in picked:
            c = curated.get(r["pitch_id"])
            if c is None or c["pitch_call_code"] != "B":
                missing += 1
                continue
            entries.append({"pitch_id": r["pitch_id"], "batter_id": str(c["batter_id"]), "pitcher_id": str(c["pitcher_id"]),
                            "source_code": "B", "code": "W", "source_velocity_kmh": float(c["velocity_kmh"]),
                            "naver_pitch_id": r["naver_pitch_id"], "naver_count_after": r["naver_count_after"],
                            "match_status": r["match_status"], "ends_pa": bool(c["is_pa_terminal"])})
        entries.sort(key=lambda e: e["pitch_id"])
        w_rows = sum(r["season"] == season and r["naver_code"] == "W" for r in rows)
        stats = {"naver_W": w_rows, "naver_W_vb_B": len(picked), "corrections": len(entries),
                 "ends_pa": sum(e["ends_pa"] for e in entries), "not_B_in_curated": missing}
        table["seasons"][season] = {"source": "naver_relay", "rule": RULE,
                                    "input": "analysis/sbj_location/results/bunt_attempts_2025_2026.csv (PR #32)",
                                    "stats": stats, "pitches": entries}
        print(season, tm.json.dumps(stats), flush=True)
    table["seasons"] = dict(sorted(table["seasons"].items()))
    tm.write_table(table)


if __name__ == "__main__":
    main()
