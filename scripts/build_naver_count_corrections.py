"""Write data/corrections/vb_count_corrections.json (and the audit's call changes) from the Naver count audit.

    PYTHONPATH=src python scripts/build_naver_count_corrections.py <naver_count_audit.csv> [seasons...]

Input: analysis/sbj_location/naver_count_audit.py. A plate appearance becomes a row only when its status is
`fix_pass`: the Naver start count (a count a pinch hitter inherits) and pitch-clock violation calls, replayed
through the parser's count rules, give the Naver count before every pitch. The row keeps the batter, pitcher and
pitch codes it was derived from; the parser (collector.count_corrections) and scripts/apply_call_corrections.py
apply it only while the plate appearance still has exactly those. A listed season is rebuilt whole from the input.

Call changes of a passing plate appearance go to data/corrections/vb_bunt_foul_corrections.json:
  * VB B that Naver calls W: a bunt-foul row (`source: naver_relay`, `match_status: naver_count_audit`) in a
    supplement with this input, replacing only this input's earlier rows (build_naver_bunt_corrections.merge_season);
  * VB W that Naver calls B: the pitch is listed in the season's `naver_rejected` and its TrackMan row is removed
    (build_trackman_bunt_corrections.py keeps it out on a rebuild). A W from a Naver input is never rejected here.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

from visualbaseball.collector import COUNT_CORRECTIONS
from visualbaseball.curated import load_rows

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_trackman_bunt_corrections as tm  # noqa: E402

AUDIT_STATUS = "naver_count_audit"
CALL_RULE = ("Naver relay call W (bunt foul) for a VB B in a plate appearance whose counts, with the audit's count "
             "corrections, equal the Naver counts before every pitch (analysis/sbj_location/naver_count_audit.py).")
RULE = ("Naver relay running count (currentGameState): a plate appearance starts at the count of its first relay line "
        "(a pinch hitter inherits the count) and a pitch-clock violation adds a ball (pitcher) or strike (batter) before "
        "the next pitch. Used only when these, replayed through the parser's count rules on the VB pitch codes, equal "
        "the Naver count before every pitch of the plate appearance.")
HEADER = {"description": "Plate-appearance count corrections for count events Visual Baseball does not record as pitches. "
                         "Applied by the parser (collector.count_corrections) and scripts/apply_call_corrections.py.",
          "fields": {"start": "balls, strikes before the first VB pitch", "inserts": "calls added before VB pitch number before_pitch",
                     "source_codes": "VB pitch codes of the plate appearance the row applies to (after bunt-foul corrections)"}}


def _inserts(text: str) -> list[dict]:
    return [{"before_pitch": int(t[:-1]), "code": t[-1]} for t in text.split()]


def call_changes(table: dict, season: str, rows: list[dict], curated: dict[str, list[dict]], label: str) -> Counter:
    """Apply the passing rows' call changes to the bunt-foul table body of this season."""
    stats, adds, rejects = Counter(), [], []
    for r in rows:
        pa = {int(x["pitch_number"]): x for x in curated.get(r["pa_id"], [])}
        for call in r["calls"].split():
            n, code = int(call[:-1]), call[-1]; x = pa[n]
            entry = {"pitch_id": x["pitch_id"], "batter_id": str(x["batter_id"]), "pitcher_id": str(x["pitcher_id"]),
                     "source_code": "B" if code == "W" else "W", "code": code, "source_velocity_kmh": float(x["velocity_kmh"])}
            if code == "W":
                adds.append({**entry, "match_status": AUDIT_STATUS, "ends_pa": bool(x["is_pa_terminal"])})
            else:
                rejects.append({**entry, "reason": "Naver relay calls B; counts equal Naver after the change"})
    body = table["seasons"][season]
    trackman_season = body.get("source") == "trackman"  # 2025-2026 rows carry no per-row source but are all Naver
    naver_rows = {e["pitch_id"] for e in body.get("pitches", []) if e.get("match_status") != AUDIT_STATUS
                  and (e.get("source") == "naver_relay" or not trackman_season)}
    kept_rejects = [e for e in rejects if e["pitch_id"] not in naver_rows]
    stats["reject_conflicts_naver_row"] = len(rejects) - len(kept_rejects)
    rejected_ids = {e["pitch_id"] for e in kept_rejects}
    trackman_ids = {e["pitch_id"] for e in body.get("pitches", []) if "source" not in e} if trackman_season else set()
    stats["rejected_trackman_rows"] = len(rejected_ids & trackman_ids)
    body = {**body, "pitches": [e for e in body.get("pitches", []) if e["pitch_id"] not in rejected_ids & trackman_ids]}
    if kept_rejects or body.get("naver_rejected"):
        body["naver_rejected"] = sorted(kept_rejects, key=lambda e: e["pitch_id"])
    meta = {"rule": CALL_RULE, "input": label, "stats": {"bunt_fouls": len(adds)}}
    # Only this audit's own rows (match_status naver_count_audit) are replaced; other Naver inputs stay.
    others = [e for e in body["pitches"] if e.get("match_status") != AUDIT_STATUS]
    have = {e["pitch_id"] for e in others}
    new = [{**e, "source": "naver_relay"} for e in adds if e["pitch_id"] not in have]
    stats["bunt_fouls_already_in_table"] = len(adds) - len(new)
    supplements = [x for x in body.get("supplements", []) if x.get("input") != label]
    if new:
        supplements.append({"source": "naver_relay", **meta})
    head = {k: v for k, v in body.items() if k not in ("pitches", "supplements")}
    table["seasons"][season] = {**head, **({"supplements": supplements} if supplements else {}),
                                "pitches": sorted(others + new, key=lambda e: e["pitch_id"])}
    stats.update(bunt_fouls=len(new), rejected=len(kept_rejects))
    return stats


def main() -> None:
    source, seasons = Path(sys.argv[1]), sys.argv[2:]
    rows = list(csv.DictReader(source.open(encoding="utf-8")))
    bunt = tm.json.loads(tm.OUT.read_text(encoding="utf-8"))
    seasons = seasons or sorted({r["season"] for r in rows})
    table = json.loads(COUNT_CORRECTIONS.read_text(encoding="utf-8")) if COUNT_CORRECTIONS.exists() else {"seasons": {}}
    table.update(HEADER)
    try:
        label = source.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        label = source.name
    for season in seasons:
        picked = [r for r in rows if r["season"] == season and r["status"] == "fix_pass"]
        curated: dict[str, list[dict]] = {}
        for r in load_rows(ROOT, "pitches", int(season), columns=["pitch_id", "pa_id", "pitch_number", "pitch_call_code", "batter_id",
                                                               "pitcher_id", "velocity_kmh", "is_pa_terminal"]):
            curated.setdefault(r["pa_id"], []).append(r)
        entries, verified, stats = [], [], Counter()
        for r in picked:
            pa = sorted(curated.get(r["pa_id"], []), key=lambda x: int(x["pitch_number"]))
            codes = "".join(str(x["pitch_call_code"] or "").upper() for x in pa)
            # Curated holds the audit's source codes before scripts/apply_call_corrections.py and the fixed codes after it.
            if not pa or codes not in (r["source_codes"], r["fixed_codes"]) or (str(pa[0]["batter_id"]), str(pa[0]["pitcher_id"])) != (r["batter_id"], r["pitcher_id"]):
                stats["not_matching_curated"] += 1
                continue
            verified.append(r)
            for k in r["kind"].split("+"):
                stats[k] += 1
            b, s = (int(x) for x in r["start"].split("-"))
            if (b, s) == (0, 0) and not r["inserts"]:
                continue  # call changes only; they go to the bunt-foul table
            entries.append({"pa_id": r["pa_id"], "batter_id": r["batter_id"], "pitcher_id": r["pitcher_id"], "source_codes": r["fixed_codes"],
                            "start": [b, s], "inserts": _inserts(r["inserts"]), "kind": r["kind"]})
        entries.sort(key=lambda e: e["pa_id"])
        stats.update(fix_pass=len(picked), count_corrections=len(entries),
                     unexplained=sum(r["season"] == season and r["status"] == "unexplained" for r in rows))
        if season in bunt["seasons"]:
            calls = [r for r in verified if r["calls"]]
            stats.update({f"calls_{k}": v for k, v in call_changes(bunt, season, calls, curated, label).items()})
        table["seasons"][season] = {"source": "naver_relay", "rule": RULE, "input": label, "stats": dict(sorted(stats.items())), "pas": entries}
        print(season, json.dumps(dict(sorted(stats.items()))), flush=True)
    table["seasons"] = dict(sorted(table["seasons"].items()))
    body = {k: table[k] for k in ("description", "fields")} | {"seasons": table["seasons"]}
    COUNT_CORRECTIONS.write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tm.write_table(bunt)


if __name__ == "__main__":
    main()
