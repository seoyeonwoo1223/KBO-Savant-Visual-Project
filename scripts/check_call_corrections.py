"""Read-only harness check: is committed curated in step with data/corrections/vb_bunt_foul_corrections.json?

    PYTHONPATH=src python scripts/check_call_corrections.py [seasons...]     # exit 1 unless every season is clean

Per season it counts
  table         pitches listed in the correction table
  applied       table pitches whose curated code is the corrected code (W)
  pending       table pitches still carrying the source code (B): run scripts/apply_call_corrections.py
  stale         table pitches missing from curated or carrying any other code (table and data disagree)
  untracked_W   curated W pitches that the table does not list
  V             curated V pitches (bunt swing-and-miss)
  count_errors  plate appearances holding W or V whose stored balls/strikes do not follow the parser's
                state rules (W and V add a strike; the last pitch ends at 0-0)
A season is clean when pending, stale, untracked_W and count_errors are all 0. Only plate appearances with
W or V are recounted: those are the ones the correction touches.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from visualbaseball.collector import CALL_CORRECTIONS
from visualbaseball.curated import load_rows
from visualbaseball.state_machine import GameState

ROOT = Path(__file__).resolve().parents[1]
SEASONS = tuple(range(2019, 2027))
COLUMNS = ["pitch_id", "pa_id", "pitch_number", "pitch_call_code",
           "balls_before", "strikes_before", "balls_after", "strikes_after"]


def expected_counts(codes: list[str]) -> list[tuple[int, int, int, int]]:
    state, out = GameState(), []
    for i, code in enumerate(codes):
        before = (state.balls, state.strikes)
        if i == len(codes) - 1:
            state.balls = state.strikes = 0
        else:
            state.apply_non_terminal_pitch(code)
        out.append((*before, state.balls, state.strikes))
    return out


def check_season(root: Path, season: int, table: dict | None = None) -> dict:
    table = table if table is not None else json.loads(CALL_CORRECTIONS.read_text(encoding="utf-8"))["seasons"]
    fixes = {row["pitch_id"]: row for row in table.get(str(season), {}).get("pitches", [])}
    rows = load_rows(root, "pitches", season, columns=COLUMNS)
    code = {r["pitch_id"]: str(r["pitch_call_code"] or "").upper() for r in rows}
    result = {"table": len(fixes), "applied": 0, "pending": 0, "stale": 0}
    for pitch_id, fix in fixes.items():
        current = code.get(pitch_id)
        result["applied" if current == fix["code"] else "pending" if current == fix["source_code"] else "stale"] += 1
    result["untracked_W"] = sum(c == "W" and p not in fixes for p, c in code.items())
    result["V"] = sum(c == "V" for c in code.values())
    by_pa: dict[str, list[dict]] = defaultdict(list)
    touched = {r["pa_id"] for r in rows if code[r["pitch_id"]] in {"W", "V"}}
    for r in rows:
        if r["pa_id"] in touched:
            by_pa[r["pa_id"]].append(r)
    errors = 0
    for pa in by_pa.values():
        pa.sort(key=lambda r: int(r["pitch_number"]))
        stored = [(int(r["balls_before"]), int(r["strikes_before"]), int(r["balls_after"]), int(r["strikes_after"])) for r in pa]
        errors += stored != expected_counts([code[r["pitch_id"]] for r in pa])
    result["count_errors"] = errors
    result["clean"] = not (result["pending"] or result["stale"] or result["untracked_W"] or errors)
    return result


def main() -> None:
    seasons = [int(s) for s in sys.argv[1:]] or list(SEASONS)
    table = json.loads(CALL_CORRECTIONS.read_text(encoding="utf-8"))["seasons"]
    clean = True
    for season in seasons:
        result = check_season(ROOT, season, table)
        clean &= result["clean"]
        print(season, json.dumps(result), flush=True)
    sys.exit(0 if clean else 1)


if __name__ == "__main__":
    main()
