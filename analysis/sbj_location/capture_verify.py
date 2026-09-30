"""Check the independent-verification list (results/capture_list.csv) against Naver inning relays (read-only).

    PYTHONPATH=src python analysis/sbj_location/capture_verify.py   # results/capture_verify.csv

Each listed VB pitch is joined to Naver with the KIA home join (naver_kia_home_bunts.join: half-inning PA ordinal key,
speed within 1 km/h, pitcher-less fallback). The row reports the Naver code and short call word of that pitch, both
plate appearances as `<number><code>:<speed>` sequences with counts, and the Naver PA result word. Counts are the thing
under test, never a join condition. Only codes and short words (<= 12 characters) enter the output.
Relays are cached under data/raw/naver/relay_raw (gitignored), one request per second.
"""
from __future__ import annotations

import csv, sys
from collections import defaultdict

from naver_kia_home_bunts import VB_COLS, join
from naver_queue_verify import RESULTS, ROOT, game_pitches, relay
from visualbaseball.curated import load_rows

SOURCE = RESULTS / "capture_list.csv"
OUT = RESULTS / "capture_verify.csv"
COLS = VB_COLS + ["velocity_kmh", "balls_after", "strikes_after"]
RESULT_TYPES = {13, 23}


def pa_results(game_id: str, innings: set[int]) -> dict[tuple, str]:
    """(inning, half, pa_no) -> short Naver PA result word (text after 'name : ')."""
    out = {}
    for inning in innings:
        for pa in (relay(game_id, inning) or {}).get("textRelays") or []:
            words = [str(o.get("text") or "").split(":", 1)[-1].strip()[:12] for o in sorted(pa.get("textOptions") or [], key=lambda o: o["seqno"])
                     if o.get("type") in RESULT_TYPES]
            if words:
                out[(int(pa["inn"]), "top" if str(pa["homeOrAway"]) == "0" else "bottom", int(pa["no"]))] = " / ".join(words)
    return out


def seq_naver(pa: list[dict]) -> str:
    return " ".join(f"{n['pitch_num']}{n['code']}:{n['speed']}({n['count_before']})" for n in sorted(pa, key=lambda n: n["pitch_num"]))


def seq_vb(pa: list[dict]) -> str:
    return " ".join(f"{int(r['pitch_number'])}{r['pitch_call_code']}:{r['velocity_kmh']:.0f}({r['balls_before']}-{r['strikes_before']})"
                    for r in sorted(pa, key=lambda r: int(r["pitch_number"])))


def main() -> None:
    wanted = list(csv.DictReader(SOURCE.open(encoding="utf-8-sig")))
    by_game = defaultdict(list)
    for w in wanted:
        by_game[w["game_id"]].append(w)
    rows = []
    for game_id, items in sorted(by_game.items()):
        naver, failed = game_pitches(game_id)
        vb = list(load_rows(ROOT, "pitches", int(game_id[:4]), game_id=game_id, columns=sorted(set(COLS))))
        joined = join(vb, naver) if naver else {}
        by_id = {r["pitch_id"]: r for r in vb}
        vb_pa = defaultdict(list)
        for r in vb:
            vb_pa[r["pa_id"]].append(r)
        naver_pa = defaultdict(list)
        for n in naver:
            naver_pa[(n["inning"], n["half"], n["pa_no"])].append(n)
        results = pa_results(game_id, {int(w["inning"]) for w in items}) if naver else {}
        for w in items:
            v = by_id.get(w["pitch_id"])
            status, n = joined.get(w["pitch_id"], ("relay_incomplete" if failed else "not_in_curated", None))
            key = (n["inning"], n["half"], n["pa_no"]) if n else None
            rows.append({"priority": w["priority"], "season": w["season"], "pitch_id": w["pitch_id"],
                         "vb_call": v["pitch_call_code"] if v else "", "vb_count_before": f"{v['balls_before']}-{v['strikes_before']}" if v else "",
                         "match_status": status, "naver_code": n["code"] if n else "", "naver_word": n["word"] if n else "",
                         "naver_count_before": n["count_before"] if n else "", "naver_count_after": n["count_after"] if n else "",
                         "vb_pa": seq_vb(vb_pa[v["pa_id"]]) if v else "", "naver_pa": seq_naver(naver_pa[key]) if key else "",
                         "naver_pa_result": results.get(key, "") if key else "", "vb_pa_result": w["pa_result"],
                         "failed_innings": " ".join(map(str, failed))})
        print(game_id, "failed" if failed else "ok", flush=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0])); wr.writeheader(); wr.writerows(rows)


if __name__ == "__main__":
    main()
