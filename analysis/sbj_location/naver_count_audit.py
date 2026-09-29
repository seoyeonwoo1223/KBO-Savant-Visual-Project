"""Compare every VB plate-appearance count with the Naver relay count, and derive count corrections (read-only).

    PYTHONPATH=src python analysis/sbj_location/naver_count_audit.py GAMES_JSON [seasons...]
        -> results/naver_count_audit_2019_2026.csv, results/naver_count_audit_2019_2026_summary.json

GAMES_JSON lists the games to audit ({"<season>": [game_id, ...]}); relays must already be cached under
data/raw/naver/relay_raw (naver_kia_home_bunts.fetch). A game with a missing inning is not used.

Naver records the running count on every relay line (currentGameState), not only on pitches. So the true count
before each pitch is the state of the line just before it; the plate appearance starts at the state of its first
line. Two count events have no VB pitch row:
  * a pinch hitter (or any batter) replacing the batter mid-count inherits the count: Naver starts the new plate
    appearance at that count and keeps numbering pitches; VB starts a new plate appearance at 0-0 and pitch 1;
  * a pitch-clock violation ("N구 피치클락 투수위반 볼" / "타자위반 스트라이크") adds a ball or strike and takes a
    pitch number, but is not a pitch.
Naver pitches are therefore renumbered by their order inside the plate appearance before the VB join
(naver_kia_home_bunts.join: half-inning PA ordinal, batter, pitcher, number, speed within 1 km/h).

For each VB plate appearance whose pitches all join one Naver plate appearance of the same length, the counts the
parser would give (current codes, V/W as strikes) are compared with Naver. A difference becomes a correction only
when the Naver start count and violation calls, replayed through the parser's rules, reproduce the Naver count
before every pitch (gate). Anything else is reported, never corrected. Only codes and short words are stored.
"""
from __future__ import annotations

import csv, json, sys
from collections import Counter, defaultdict

from naver_kia_home_bunts import VB_COLS, join
from naver_queue_verify import RESULTS, ROOT, final_inning, relay
from visualbaseball.curated import load_rows

sys.path.insert(0, str(ROOT / "scripts"))
from apply_call_corrections import _counts  # noqa: E402

OUT_CSV = RESULTS / "naver_count_audit_2019_2026.csv"
OUT_SUMMARY = RESULTS / "naver_count_audit_2019_2026_summary.json"
CODE_MAP = {"H": "X"}  # Naver in-play is VB X
COLUMNS = ("season", "game_id", "pa_id", "status", "kind", "batter_id", "pitcher_id", "source_codes", "start", "inserts",
           "vb_counts", "naver_counts", "naver_pa")


def _state(option: dict) -> tuple[int, int]:
    st = option.get("currentGameState") or {}
    return int(st.get("ball") or 0), int(st.get("strike") or 0)


def violation(text: str) -> str | None:
    if "피치클락" not in text:
        return None
    return "B" if "투수위반" in text else "S" if "타자위반" in text else None


def naver_game(game_id: str) -> tuple[list[dict], dict, list[int]]:
    """Naver pitches renumbered inside each plate appearance, plus per-PA start count and violation calls."""
    first = relay(game_id, 1)
    if first is None:
        return [], {}, [1]
    pitches, pas, failed, seen = [], {}, [], set()
    for inning in range(1, final_inning(first) + 1):
        data = first if inning == 1 else relay(game_id, inning)
        if data is None:
            failed.append(inning); continue
        for pa in data.get("textRelays") or []:
            key = (int(pa["inn"]), "top" if str(pa["homeOrAway"]) == "0" else "bottom", int(pa["no"]))
            if key in seen:
                continue
            seen.add(key)
            options = sorted(pa.get("textOptions") or [], key=lambda o: int(o.get("seqno") or 0))
            if not options:
                continue
            start, prev, order, inserts, unexplained = _state(options[0]), _state(options[0]), 0, [], []
            for o in options:
                now = _state(o)
                if o.get("pitchNum") is not None and o.get("pitchResult") is not None:
                    order += 1; st = o.get("currentGameState") or {}
                    pitches.append({"inning": key[0], "half": key[1], "pa_no": key[2], "pitch_num": order, "naver_pitch_num": int(o["pitchNum"]),
                                    "code": str(o["pitchResult"]), "speed": o.get("speed"), "batter": str(st.get("batter") or ""),
                                    "pitcher": str(st.get("pitcher") or ""), "before": prev, "after": now})
                elif now != prev:
                    call = violation(str(o.get("text") or ""))
                    if call:
                        inserts.append({"before_pitch": order + 1, "code": call})
                    elif order:  # changes after the PA's first pitch that no pitch explains (a result line after the last pitch is ignored below)
                        unexplained.append(order)
                prev = now
            pas[key] = {"start": start, "inserts": inserts, "unexplained": [u for u in unexplained if u < order], "pitches": order}
    return pitches, pas, failed


def audit_game(game_id: str, vb: list[dict]) -> tuple[list[dict], Counter]:
    naver, pas, failed = naver_game(game_id)
    st = Counter()
    if failed or not naver:
        st["games_incomplete"] += 1
        return [], st
    joined = join(vb, naver)
    by_pa = defaultdict(list)
    for r in vb:
        by_pa[r["pa_id"]].append(r)
    rows = []
    for pa_id, prs in sorted(by_pa.items()):
        prs.sort(key=lambda r: int(r["pitch_number"]))
        codes = [str(r["pitch_call_code"] or "").upper() for r in prs]
        ns = [joined[r["pitch_id"]][1] for r in prs]
        st["vb_pas"] += 1
        for r, n in zip(prs, ns):
            if n is not None and CODE_MAP.get(n["code"], n["code"]) != str(r["pitch_call_code"] or "").upper():
                st[f"code_{str(r['pitch_call_code']).upper()}_naver_{n['code']}"] += 1
        base = {"season": int(game_id[:4]), "game_id": game_id, "pa_id": pa_id, "batter_id": str(prs[0]["batter_id"]),
                "pitcher_id": str(prs[0]["pitcher_id"]), "source_codes": "".join(codes),
                "vb_counts": " ".join(f"{b}-{s}" for b, s, _, _ in _counts(codes))}
        if any(n is None for n in ns) or len({(n["inning"], n["half"], n["pa_no"]) for n in ns}) != 1:
            st["pa_unjoined"] += 1
            if any(r["pitch_call_code"] for r in prs):
                rows.append({**base, "status": "unjoined", "kind": "", "start": "", "inserts": "", "naver_counts": "", "naver_pa": ""})
            continue
        key = (ns[0]["inning"], ns[0]["half"], ns[0]["pa_no"]); info = pas[key]
        naver_counts = [n["before"] for n in ns]
        seq = " ".join(f"{n['naver_pitch_num']}{n['code']}" for n in ns)
        if info["pitches"] != len(prs):
            st["pa_length_differs"] += 1
            rows.append({**base, "status": "length_differs", "kind": "", "start": "", "inserts": "", "naver_counts": " ".join(f"{b}-{s}" for b, s in naver_counts), "naver_pa": seq})
            continue
        plain = [(b, s) for b, s, _, _ in _counts(codes)]
        if plain == naver_counts:
            st["pa_count_equal"] += 1; continue
        fix = {"start": list(info["start"]), "inserts": info["inserts"]}
        kinds = (["inherited_count"] if info["start"] != (0, 0) else []) + (["pitch_clock"] if info["inserts"] else [])
        fixed = [(b, s) for b, s, _, _ in _counts(codes, fix=fix)]
        status = "fix_pass" if kinds and fixed == naver_counts and not info["unexplained"] else "unexplained"
        st[f"pa_{status}"] += 1
        for k in kinds:
            st[f"{status}_{k}"] += 1
        rows.append({**base, "status": status, "kind": "+".join(kinds), "start": f"{fix['start'][0]}-{fix['start'][1]}",
                     "inserts": " ".join(f"{i['before_pitch']}{i['code']}" for i in fix["inserts"]),
                     "naver_counts": " ".join(f"{b}-{s}" for b, s in naver_counts), "naver_pa": seq})
    return rows, st


def main() -> None:
    games = json.loads(open(sys.argv[1], encoding="utf-8").read())
    seasons = [s for s in sys.argv[2:]] or sorted(games)
    rows, summary = [], {"definition": {"doc": __doc__.split("\n\n")[2].strip(), "caveat": "Naver and VB may share an upstream source"}, "seasons": {}}
    for season in seasons:
        wanted = set(games[season]); vb_all = defaultdict(list)
        for r in load_rows(ROOT, "pitches", int(season), columns=sorted(set(VB_COLS + ["balls_after", "strikes_after"]))):
            if r["game_id"] in wanted:
                vb_all[r["game_id"]].append(r)
        st, incomplete = Counter(), []
        for game_id in sorted(wanted):
            got, c = audit_game(game_id, vb_all[game_id])
            if c["games_incomplete"]:
                incomplete.append(game_id)
            rows += got; st.update(c)
        st.pop("games_incomplete", None)
        summary["seasons"][season] = {"games": len(wanted), "games_used": len(wanted) - len(incomplete), "incomplete_games": incomplete,
                                      "stats": dict(sorted(st.items()))}
        print(season, json.dumps(summary["seasons"][season]["stats"], ensure_ascii=False), "incomplete", len(incomplete), flush=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=COLUMNS); wr.writeheader(); wr.writerows(rows)
    OUT_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
