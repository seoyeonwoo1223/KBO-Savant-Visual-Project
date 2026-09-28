"""Build the VB 'B' -> bunt-foul correction table from TrackMan count transitions (2019-2024).

    PYTHONPATH=src python scripts/build_trackman_bunt_corrections.py [seasons...]

Visual Baseball records a bunt foul as `B` (ball). A Naver relay sample (42 of 42 GPT-checked pitches and
13 of 13 relay `W` pitches in analysis/sbj_location) showed these pitches as `W/번트파울`. TrackMan has no
per-pitch call, so a candidate is selected only from its count transition:

  * the VB pitch is `B` and is not the last pitch of its plate appearance;
  * it is matched one-to-one to a TrackMan pitch (PR #29 run alignment with trajectory speed and a
    per-game offset, analysis/sbj_location/trackman_harness.py);
  * the next VB pitch of the same plate appearance is matched to the next TrackMan pitch of the same
    plate appearance, and between the two TrackMan pitches balls stay the same and strikes rise by one.

Whether a selected pitch was a bunt foul or an unrecorded called strike, its count effect is one strike and
it is not a swing/take decision, so the parser gives it code `W` (see parser.py). The table is the only
output: data/corrections/vb_bunt_fouls_trackman.json. Terminal `B` pitches (a two-strike bunt foul ends the
plate appearance) have no next TrackMan pitch and are not selected.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis/trajectory_audit"))
sys.path.insert(0, str(ROOT / "analysis/sbj_location"))
import pa_flow_strict as pf  # noqa: E402
import trackman_harness as th  # noqa: E402
from visualbaseball.curated import load_rows  # noqa: E402

OUT = ROOT / "data" / "corrections" / "vb_bunt_fouls_trackman.json"
SEASONS = tuple(range(2019, 2025))


def season_entries(season: int) -> tuple[list[dict], dict]:
    vb, tm, games, _ = pf.load(season)
    t = pd.DataFrame(load_rows(ROOT, "pitches", season, columns=["pitch_id", "vx0", "vy0", "vz0", "trajectory_valid", "is_pa_terminal"]))
    t = t.set_index("pitch_id").reindex(vb.pitch_id)
    ok = t.trajectory_valid.fillna(False).astype(bool).to_numpy()
    traj = np.sqrt(t.vx0.astype(float) ** 2 + t.vy0.astype(float) ** 2 + t.vz0.astype(float) ** 2).to_numpy() * 1.09728
    m, _, _, _ = th.run(vb, tm, games, pd.Series(np.where(ok, traj, np.nan), index=vb.index), per_game=True)
    partner = dict(zip(m.vi, m.ti))
    code = vb.pitch_call_code.fillna("").str.upper().to_numpy()
    terminal = t.is_pa_terminal.fillna(False).astype(bool).to_numpy()
    entries, rejected = [], {"terminal_B": 0, "next_not_matched": 0}
    for vi, ti in partner.items():
        if code[vi] != "B":
            continue
        if terminal[vi]:
            rejected["terminal_B"] += 1
            continue
        nvi = vi + 1
        if nvi >= len(vb) or vb.pa_id.iat[nvi] != vb.pa_id.iat[vi] or partner.get(nvi) != ti + 1:
            rejected["next_not_matched"] += 1
            continue
        a, b = tm.iloc[ti], tm.iloc[ti + 1]
        if b.game_id != a.game_id or int(b.pitch_of_pa) != int(a.pitch_of_pa) + 1:
            rejected["next_not_matched"] += 1
            continue
        if int(b.balls_before) != int(a.balls_before) or int(b.strikes_before) != int(a.strikes_before) + 1:
            continue
        r = vb.iloc[vi]
        entries.append({
            "pitch_id": r.pitch_id, "batter_id": r.batter_id, "pitcher_id": r.pitcher_id,
            "source_code": "B", "code": "W", "source_velocity_kmh": float(r.velocity_kmh),
            "trackman_id": str(a.trackman_id), "trackman_next_id": str(b.trackman_id),
            "trackman_count_before": f"{int(a.balls_before)}-{int(a.strikes_before)}",
            "trackman_count_next": f"{int(b.balls_before)}-{int(b.strikes_before)}",
        })
    entries.sort(key=lambda e: e["pitch_id"])
    return entries, {"vb_pitches": int(len(vb)), "matched": int(len(partner)), "corrections": len(entries), **rejected}


def main() -> None:
    seasons = [int(s) for s in sys.argv[1:]] or list(SEASONS)
    table = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"seasons": {}}
    table.update({
        "version": 1,
        "rule": "VB B (non-terminal) matched 1:1 to TrackMan; next VB pitch of the PA matched to the next TrackMan pitch; "
                "TrackMan balls unchanged and strikes +1. Applied as code W (bunt foul): not a swing or take, one strike.",
        "evidence": "analysis/sbj_location/README.md (번트 파울 레이블 정정)",
    })
    for season in seasons:
        entries, stats = season_entries(season)
        table["seasons"][str(season)] = {"stats": stats, "pitches": entries}
        print(season, json.dumps(stats), flush=True)
    table["seasons"] = dict(sorted(table["seasons"].items()))
    write_table(table)


def write_table(table: dict) -> None:
    """One pitch per line so a review diff shows exactly which pitches changed."""
    head = {k: v for k, v in table.items() if k != "seasons"}
    lines = ["{" + json.dumps(head, ensure_ascii=False)[1:-1] + ', "seasons": {']
    for i, (season, body) in enumerate(table["seasons"].items()):
        rows = ",\n".join("   " + json.dumps(row, ensure_ascii=False) for row in body["pitches"])
        lines.append(f' "{season}": {{"stats": {json.dumps(body["stats"])}, "pitches": [\n{rows}\n ]}}'
                     + ("," if i < len(table["seasons"]) - 1 else ""))
    lines.append("}}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
