"""Write data/corrections/vb_count_corrections.json from the Naver count audit.

    PYTHONPATH=src python scripts/build_naver_count_corrections.py <naver_count_audit.csv> [seasons...]

Input: analysis/sbj_location/naver_count_audit.py. A plate appearance becomes a row only when its status is
`fix_pass`: the Naver start count (a count a pinch hitter inherits) and pitch-clock violation calls, replayed
through the parser's count rules, give the Naver count before every pitch. The row keeps the batter, pitcher and
pitch codes it was derived from; the parser (collector.count_corrections) and scripts/apply_call_corrections.py
apply it only while the plate appearance still has exactly those. A listed season is rebuilt whole from the input.
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


def main() -> None:
    source, seasons = Path(sys.argv[1]), sys.argv[2:]
    rows = list(csv.DictReader(source.open(encoding="utf-8")))
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
        for r in load_rows(ROOT, "pitches", int(season), columns=["pa_id", "pitch_number", "pitch_call_code", "batter_id", "pitcher_id"]):
            curated.setdefault(r["pa_id"], []).append(r)
        entries, stats = [], Counter()
        for r in picked:
            pa = sorted(curated.get(r["pa_id"], []), key=lambda x: int(x["pitch_number"]))
            codes = "".join(str(x["pitch_call_code"] or "").upper() for x in pa)
            if not pa or (codes, str(pa[0]["batter_id"]), str(pa[0]["pitcher_id"])) != (r["source_codes"], r["batter_id"], r["pitcher_id"]):
                stats["not_matching_curated"] += 1
                continue
            b, s = (int(x) for x in r["start"].split("-"))
            entries.append({"pa_id": r["pa_id"], "batter_id": r["batter_id"], "pitcher_id": r["pitcher_id"], "source_codes": r["source_codes"],
                            "start": [b, s], "inserts": _inserts(r["inserts"]), "kind": r["kind"]})
            for k in r["kind"].split("+"):
                stats[k] += 1
        entries.sort(key=lambda e: e["pa_id"])
        stats.update(fix_pass=len(picked), corrections=len(entries),
                     unexplained=sum(r["season"] == season and r["status"] == "unexplained" for r in rows))
        table["seasons"][season] = {"source": "naver_relay", "rule": RULE, "input": label, "stats": dict(sorted(stats.items())), "pas": entries}
        print(season, json.dumps(dict(sorted(stats.items()))), flush=True)
    table["seasons"] = dict(sorted(table["seasons"].items()))
    body = {k: table[k] for k in ("description", "fields")} | {"seasons": table["seasons"]}
    COUNT_CORRECTIONS.write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
