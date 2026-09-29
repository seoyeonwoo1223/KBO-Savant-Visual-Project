"""Naver relay bunt fouls in 2019-2024 KIA home games (no TrackMan there), joined to VB and count-gated.

    PYTHONPATH=src python analysis/sbj_location/naver_kia_home_bunts.py fetch            # cache every inning (1 req/s)
    PYTHONPATH=src python analysis/sbj_location/naver_kia_home_bunts.py build [seasons]  # results/naver_bunt_fouls_kia_home.csv

Design: naver_bunt_extension_design.md section 2, gates K1-K4 in sbj_validation_gates.md. Relays are cached
unmodified under data/raw/naver/relay_raw (gitignored). A game with any missing inning is not used (K1).
"""
from __future__ import annotations

import csv, json, sys
from collections import Counter, defaultdict
from pathlib import Path

from naver_queue_verify import ROOT, RESULTS, game_pitches
from visualbaseball.collector import CALL_CORRECTIONS
from visualbaseball.curated import load_rows

sys.path.insert(0, str(ROOT / "scripts"))
from apply_call_corrections import _counts  # noqa: E402  (parser count rules, V is a strike)

SEASONS = tuple(range(2019, 2025))
COVERAGE = RESULTS / "naver_kia_home_fetch_2019_2024.json"
OUT_CSV = RESULTS / "naver_bunt_fouls_kia_home_2019_2024.csv"
OUT_SUMMARY = RESULTS / "naver_bunt_fouls_kia_home_2019_2024_summary.json"
VB_COLS = ["pitch_id", "game_id", "pa_id", "inning", "inning_half", "batter_id", "pitcher_id", "pitch_number",
           "velocity_kmh", "pitch_call_code", "balls_before", "strikes_before", "is_pa_terminal"]
COLUMNS = ("season", "game_id", "pitch_id", "naver_pitch_id", "naver_code", "naver_phrase", "vb_call", "vb_count_before",
           "naver_count_before", "naver_count_after", "match_status", "gate", "ends_pa")


def target_games(seasons=SEASONS) -> list[str]:
    return sorted(r["game_id"] for s in seasons for r in load_rows(ROOT, "games", s, columns=["game_id"]) if r["game_id"][10:12] == "HT")


def fetch() -> None:
    status = {}
    for i, game_id in enumerate(target_games(), 1):
        pitches, failed = game_pitches(game_id)
        status[game_id] = {"pitches": len(pitches), "failed_innings": failed}
        if i % 20 == 0 or failed:
            print(i, game_id, len(pitches), failed, flush=True)
    by_season = defaultdict(Counter)
    for g, v in status.items():
        by_season[g[:4]]["games"] += 1; by_season[g[:4]]["incomplete"] += bool(v["failed_innings"])
    COVERAGE.write_text(json.dumps({"seasons": {s: dict(c) for s, c in sorted(by_season.items())},
                                    "incomplete_games": {g: v["failed_innings"] for g, v in status.items() if v["failed_innings"]}},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    print({s: dict(c) for s, c in sorted(by_season.items())})


def _speed_ok(n: dict, v: dict) -> bool:
    try:
        return abs(float(n["speed"]) - float(v["velocity_kmh"])) <= 1
    except (TypeError, ValueError):
        return False


def join(vb: list[dict], naver: list[dict]) -> dict[str, tuple[str, dict | None]]:
    """VB pitch -> (status, Naver pitch). matched_context uses the PR #32 key; matched_without_pitcher drops the
    pitcher (Naver can switch the pitcher ID inside a PA, analysis 4e); a Naver pitch claimed twice is ambiguous."""
    k5, k4 = defaultdict(list), defaultdict(list)
    for n in naver:
        k5[(n["inning"], n["half"], n["batter"], n["pitcher"], n["pitch_num"])].append(n)
        k4[(n["inning"], n["half"], n["batter"], n["pitch_num"])].append(n)
    out = {}
    for v in vb:
        key = (int(v["inning"]), v["inning_half"], str(v["batter_id"]), str(v["pitcher_id"]), int(v["pitch_number"]))
        c = [n for n in k5.get(key, []) if _speed_ok(n, v)]
        if len(c) == 1:
            out[v["pitch_id"]] = ("matched_context", c[0]); continue
        if c:
            out[v["pitch_id"]] = ("ambiguous", None); continue
        c = [n for n in k4.get(key[:3] + key[4:], []) if _speed_ok(n, v)]
        out[v["pitch_id"]] = ("matched_without_pitcher", c[0]) if len(c) == 1 else ("ambiguous", None) if c else ("unmatched", None)
    claimed = Counter(id(n) for s, n in out.values() if n is not None)
    return {p: (("ambiguous", None) if n is not None and claimed[id(n)] > 1 else (s, n)) for p, (s, n) in out.items()}


def pa_gate(rows: list[dict], joined: dict, fixed: set[str]) -> str:
    """K3: with the selected W pitches recoded, every pitch of the VB PA must join to the same Naver PA, the PA
    lengths must agree, and every recounted VB count-before must equal the Naver count-before."""
    rows = sorted(rows, key=lambda r: int(r["pitch_number"]))
    naver = [joined[r["pitch_id"]][1] for r in rows]
    if any(n is None for n in naver):
        return "fail:unjoined_pitch"
    if len({(n["inning"], n["half"], n["pa_no"]) for n in naver}) != 1:
        return "fail:split_pa"
    if len(rows) != naver[0]["pa_len"]:
        return "fail:pa_length"
    codes = ["W" if r["pitch_id"] in fixed else str(r["pitch_call_code"] or "").upper() for r in rows]
    if any(f"{b}-{s}" != n["count_before"] for (b, s, _, _), n in zip(_counts(codes), naver)):
        return "fail:count"
    return "pass"


def build(seasons=SEASONS) -> None:
    rows, summary = [], {"definition": {"design": "naver_bunt_extension_design.md section 2", "gates": "sbj_validation_gates.md K1-K4",
                                         "games": "game_id home code HT (KIA home); no TrackMan in any of them"}, "seasons": {}}
    for season in seasons:
        games = target_games([season]); vb_all = defaultdict(list)
        for r in load_rows(ROOT, "pitches", season, columns=VB_COLS):
            if r["game_id"][10:12] == "HT":
                vb_all[r["game_id"]].append(r)
        # Pitches this table already corrected read W in curated; report them by their source call so a rerun
        # after apply_call_corrections.py selects the same rows.
        table = json.loads(CALL_CORRECTIONS.read_text(encoding="utf-8")) if CALL_CORRECTIONS.exists() else {}
        corrected = {e["pitch_id"] for e in (table.get("seasons", {}).get(str(season)) or {}).get("pitches", [])}
        st, gates, incomplete = Counter(), Counter(), []
        for game_id in games:
            naver, failed = game_pitches(game_id)
            if failed or not naver:
                incomplete.append(game_id); continue
            pa_len = Counter((n["inning"], n["half"], n["pa_no"]) for n in naver)
            for n in naver:
                n["pa_len"] = pa_len[(n["inning"], n["half"], n["pa_no"])]
            vb = vb_all[game_id]; joined = join(vb, naver); by_id = {r["pitch_id"]: r for r in vb}
            back = {id(n): p for p, (s, n) in joined.items() if n is not None}
            st["vb_pitches"] += len(vb); st.update(f"vb_{s}" for s, _ in joined.values())
            w_rows = []
            for n in naver:
                if n["code"] != "W":
                    continue
                pid = back.get(id(n)); v = by_id.get(pid) if pid else None
                w_rows.append((n, v, joined[pid][0] if pid else "unmatched"))
            source_call = lambda v: "B" if v["pitch_id"] in corrected and str(v["pitch_call_code"]).upper() == "W" else str(v["pitch_call_code"]).upper()
            fixed = {v["pitch_id"] for n, v, s in w_rows if v is not None and source_call(v) == "B"}
            by_pa = defaultdict(list)
            for r in vb:
                by_pa[r["pa_id"]].append(r)
            pa_result = {pa: pa_gate(by_pa[pa], joined, fixed) for pa in {by_id[p]["pa_id"] for p in fixed}}
            gates.update(pa_result.values())
            for n, v, s in w_rows:
                st["naver_W"] += 1; st[f"W_{s}"] += 1
                call = source_call(v) if v else ""
                st[f"W_vb_{call or 'none'}"] += 1
                gate = pa_result.get(v["pa_id"], "") if v is not None and v["pitch_id"] in fixed else ""
                rows.append({"season": season, "game_id": game_id, "pitch_id": v["pitch_id"] if v else "", "naver_pitch_id": n["pts_id"],
                             "naver_code": "W", "naver_phrase": n["word"], "vb_call": call,
                             "vb_count_before": f"{v['balls_before']}-{v['strikes_before']}" if v else "",
                             "naver_count_before": n["count_before"], "naver_count_after": n["count_after"], "match_status": s,
                             "gate": gate, "ends_pa": bool(v["is_pa_terminal"]) if v else ""})
        used = len(games) - len(incomplete); w = st["naver_W"]
        bad = st["W_unmatched"] + st["W_ambiguous"]; pas = sum(gates.values())
        summary["seasons"][str(season)] = {
            "games": len(games), "games_used": used, "incomplete_games": incomplete, "stats": dict(sorted(st.items())),
            "pa_gate": dict(sorted(gates.items())),
            "corrections": sum(1 for r in rows if r["season"] == season and r["gate"] == "pass"),
            "K1_complete": not incomplete, "K2_unmatched_or_ambiguous_share": round(bad / w, 4) if w else None, "K2_pass": bool(w) and bad / w <= 0.01,
            "K3_pa_pass_share": round(gates["pass"] / pas, 4) if pas else None, "K3_pass": bool(pas) and gates["pass"] / pas >= 0.95,
            "K4_W_per_game": round(w / used, 3) if used else None, "K4_pass": bool(used) and 0.8 <= w / used <= 1.2}
        print(season, json.dumps({k: v for k, v in summary["seasons"][str(season)].items() if k != "stats"}, ensure_ascii=False), flush=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=COLUMNS); wr.writeheader(); wr.writerows(sorted(rows, key=lambda r: (r["game_id"], r["naver_pitch_id"], r["pitch_id"])))
    OUT_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "fetch":
        fetch()
    else:
        build([int(s) for s in sys.argv[2:]] or SEASONS)
