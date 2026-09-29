"""Add Naver-relay bunt fouls (2025-2026) to data/corrections/vb_bunt_foul_corrections.json.

    PYTHONPATH=src python scripts/build_naver_bunt_corrections.py <bunt_attempts_2025_2026.csv> [seasons...]

Input is the per-pitch Naver bunt table from PR #32 (analysis/sbj_location/results/bunt_attempts_2025_2026.csv,
commit 1979b77e): Naver relay code `W` (번트파울) joined to a VB pitch. A row becomes a correction only when
Naver says `W`, VB recorded `B`, and the join is `matched_id` or `matched_context` (unmatched/ambiguous rows are
never used). Batter, pitcher and displayed velocity come from curated so the parser guard can check the raw
pitch. Unlike the TrackMan table, a two-strike bunt foul that ends the plate appearance is included.

An input with a `gate` column (analysis/sbj_location/naver_kia_home_bunts.py, 2019-2024 KIA home games that have
no TrackMan) must also pass its plate-appearance count gate; there `matched_without_pitcher` joins are accepted
only through that gate. For a season that already holds TrackMan rows, the Naver rows are merged in as a
`supplements` entry with `source: naver_relay` on each pitch; TrackMan rows are never replaced or duplicated.

A gated input replaces only what it produced earlier: the supplement with the same `input` and the naver_relay rows
of the games that input covers. Other naver_relay rows and supplements (the KIA home table next to the non-TrackMan
game table, for instance) stay as they are, so the inputs can be run one at a time in any order.
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
RULE_GATED = ("Naver relay pitchResult W (번트파울) joined to a VB pitch recorded as B (matched_context, or "
              "matched_without_pitcher), in a plate appearance whose recounted VB counts equal the Naver counts on every pitch.")
MATCHED = {"matched_id", "matched_context"}


def selected(row: dict) -> bool:
    if row["naver_code"] != "W" or row["vb_call"] != "B":
        return False
    if "gate" not in row:
        return row["match_status"] in MATCHED
    return row["gate"] == "pass" and row["match_status"] in MATCHED | {"matched_without_pitcher"}


def game_of(pitch_id: str) -> str:
    return pitch_id.split("-")[0]


def merge_season(body: dict | None, entries: list[dict], meta: dict, games: set[str] | None = None) -> tuple[dict, int]:
    """Season body with these Naver entries. A TrackMan season keeps every TrackMan row and gains a supplement;
    otherwise the season is Naver-only and is replaced as before. Returns the body and rows already present.
    With `games` (the games this input covers) only that input's own naver_relay rows and its supplement (same
    `input`) are replaced; without it every naver_relay row and supplement of the season is."""
    if not body or body.get("source") == "naver_relay":
        return {"source": "naver_relay", **meta, "pitches": entries}, 0
    own = (lambda e: e.get("source") == "naver_relay") if games is None else (
        lambda e: e.get("source") == "naver_relay" and game_of(e["pitch_id"]) in games)
    base = [e for e in body["pitches"] if not own(e)]
    have = {e["pitch_id"] for e in base}
    new = [{**e, "source": "naver_relay"} for e in entries if e["pitch_id"] not in have]
    keep = [s for s in body.get("supplements", []) if s.get("source") != "naver_relay"] if games is None else [
        s for s in body.get("supplements", []) if not (s.get("source") == "naver_relay" and s.get("input") == meta["input"])]
    supplements = keep + [{"source": "naver_relay", **meta}]
    head = {k: v for k, v in body.items() if k not in ("pitches", "supplements")}
    return {**head, "supplements": supplements, "pitches": sorted(base + new, key=lambda e: e["pitch_id"])}, len(entries) - len(new)


def main() -> None:
    source, seasons = Path(sys.argv[1]), [s for s in sys.argv[2:]] or ["2025", "2026"]
    with source.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    table = tm.json.loads(tm.OUT.read_text(encoding="utf-8"))
    table.update(tm.HEADER)
    gated = bool(rows) and "gate" in rows[0]
    try:
        label = source.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        label = source.name
    for season in seasons:
        picked = [r for r in rows if r["season"] == season and selected(r)]
        curated = {r["pitch_id"]: r for r in load_rows(ROOT, "pitches", int(season), columns=[
            "pitch_id", "batter_id", "pitcher_id", "velocity_kmh", "pitch_call_code", "is_pa_terminal"])}
        # Rows already applied to curated read W there now; keep their recorded entry so a rerun is a no-op.
        previous = {e["pitch_id"]: {k: v for k, v in e.items() if k != "source"}
                    for e in (table["seasons"].get(season) or {}).get("pitches", []) if e.get("source", "naver_relay") == "naver_relay"}
        entries, missing = [], 0
        for r in picked:
            c = curated.get(r["pitch_id"])
            if c is not None and c["pitch_call_code"] == "W" and r["pitch_id"] in previous:
                entries.append(previous[r["pitch_id"]])
                continue
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
        meta = {"rule": RULE_GATED if gated else RULE,
                "input": label if gated else "analysis/sbj_location/results/bunt_attempts_2025_2026.csv (PR #32)", "stats": stats}
        if gated:
            stats["gate_failed"] = sum(r["season"] == season and r["naver_code"] == "W" and r["vb_call"] == "B"
                                       and r["gate"].startswith("fail") for r in rows)
        scope = {r["game_id"] for r in rows if r["season"] == season} if gated else None
        body, duplicates = merge_season(table["seasons"].get(season), entries, meta, scope)
        if "supplements" in body:
            stats["already_in_table"] = duplicates
        table["seasons"][season] = body
        print(season, tm.json.dumps(stats), flush=True)
    table["seasons"] = dict(sorted(table["seasons"].items()))
    tm.write_table(table)


if __name__ == "__main__":
    main()
