"""Check the label-residual queue and KIA home relay coverage against Naver inning relays (read-only).

    PYTHONPATH=src python analysis/sbj_location/naver_queue_verify.py queue      # results/naver_queue_verify_2024_2026.csv
    PYTHONPATH=src python analysis/sbj_location/naver_queue_verify.py coverage   # results/naver_kia_home_coverage_2019_2023.json

Relays are cached unmodified under data/raw/naver/relay_raw/<season>/<game_id>/inning_N.json (gitignored), at most
one request per second, same layout as PR #32's bunt_relay_fetch.py. Only pitch codes and short call words enter
tracked outputs. A VB pitch is joined to a Naver pitch by (inning, half, batter, pitcher, pitch number) with
displayed speed within 1 km/h, the matched_context rule of PR #32's bunt_attempts.py.
"""
from __future__ import annotations

import csv, json, re, sys, time
from collections import Counter
from pathlib import Path

import requests
from visualbaseball.curated import load_rows

HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
DEST = ROOT / "data/raw/naver/relay_raw"; RESULTS = HERE / "results"
_session = requests.Session(); _session.headers.update({"User-Agent": "visualbaseball-savant-collector/1.0"}); _last = [0.0]
WORD = re.compile(r"^\d+구\s*(.+)$")


def relay(game_id: str, inning: int) -> dict | None:
    path = DEST / game_id[:4] / game_id / f"inning_{inning}.json"
    for attempt in range(4):
        if path.exists():
            try:
                payload = json.loads(path.read_bytes().decode("utf-8-sig"))
                if payload.get("code") == 200 and (payload.get("result") or {}).get("textRelayData"):
                    return payload["result"]["textRelayData"]
            except ValueError:
                pass
        if attempt == 3:
            return None
        time.sleep(max(0, 1.05 - (time.monotonic() - _last[0]))); _last[0] = time.monotonic()
        try:
            r = _session.get(f"https://api-gw.sports.naver.com/schedule/games/{game_id}{game_id[:4]}/relay?inning={inning}", timeout=30)
            r.raise_for_status(); payload = json.loads(r.content.decode("utf-8-sig"))
            if payload.get("code") == 200 and (payload.get("result") or {}).get("textRelayData"):
                path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(r.content)
        except (requests.RequestException, ValueError):
            pass
    return None


def final_inning(first: dict) -> int:
    return max(int(k) for side in (first.get("inningScore") or {}).values() for k, v in side.items() if str(v).isdigit())


def game_pitches(game_id: str) -> tuple[list[dict], list[int]]:
    """Every Naver pitch of the game with count before/after; also the innings that failed to load."""
    first = relay(game_id, 1)
    if first is None:
        return [], [1]
    out, failed, seen = [], [], set()
    for inning in range(1, final_inning(first) + 1):
        data = first if inning == 1 else relay(game_id, inning)
        if data is None:
            failed.append(inning); continue
        for pa in data.get("textRelays") or []:
            key = (int(pa["inn"]), str(pa["homeOrAway"]), int(pa["no"]))
            if key in seen:
                continue
            seen.add(key); before = (0, 0)
            for o in sorted(pa.get("textOptions") or [], key=lambda x: int(x.get("seqno") or 0)):
                if o.get("pitchNum") is None or o.get("pitchResult") is None:
                    continue
                st = o.get("currentGameState") or {}; after = (int(st.get("ball") or 0), int(st.get("strike") or 0))
                m = WORD.match(str(o.get("text") or ""))
                out.append({"inning": key[0], "half": "top" if key[1] == "0" else "bottom", "pa_no": key[2], "pitch_num": int(o["pitchNum"]),
                            "code": str(o["pitchResult"]), "word": (m.group(1) if m else "")[:12], "speed": o.get("speed"),
                            "batter": str(st.get("batter") or ""), "pitcher": str(st.get("pitcher") or ""),
                            "count_before": f"{before[0]}-{before[1]}", "count_after": f"{after[0]}-{after[1]}"})
                before = after
    return out, failed


def verify_queue() -> None:
    gpt = {r["pitch_id"]: r for r in csv.DictReader((RESULTS / "gpt_naver_queue_check_2024_2026.csv").open(encoding="utf-8"))}
    cols = ["pitch_id", "pa_id", "inning", "inning_half", "batter_id", "pitcher_id", "pitch_number", "velocity_kmh", "pitch_call_code", "balls_before", "strikes_before"]
    rows, status = [], Counter()
    for game_id in sorted({r["game_id"] for r in gpt.values()}):
        naver, failed = game_pitches(game_id)
        vb = {r["pitch_id"]: r for r in load_rows(ROOT, "pitches", int(game_id[:4]), game_id=game_id, columns=cols)}
        for pid in sorted(p for p, g in gpt.items() if g["game_id"] == game_id):
            v = vb[pid]
            def find(pitch_number):
                c = [n for n in naver if (n["inning"], n["half"], n["batter"], n["pitcher"], n["pitch_num"]) ==
                     (int(v["inning"]), v["inning_half"], str(v["batter_id"]), str(v["pitcher_id"]), pitch_number)]
                return c
            cand = [n for n in find(int(v["pitch_number"])) if n["speed"] not in (None, "") and abs(float(n["speed"]) - float(v["velocity_kmh"])) <= 1]
            st = "matched_context" if len(cand) == 1 else "ambiguous" if cand else ("relay_incomplete" if failed else "unmatched")
            status[st] += 1; n = cand[0] if len(cand) == 1 else {}
            pa = [x for x in naver if n and (x["inning"], x["half"], x["pa_no"]) == (n["inning"], n["half"], n["pa_no"])]
            nxt = [x for x in pa if n and x["pitch_num"] == n["pitch_num"] + 1]
            vb_pa = sorted((r for r in vb.values() if r["pa_id"] == v["pa_id"]), key=lambda r: r["pitch_number"])
            verdict = ("bunt_foul" if n.get("code") == "W" else "strike" if n.get("code") in {"T", "S"} else
                       "ball" if n.get("code") == "B" else n.get("code", ""))
            rows.append({"pitch_id": pid, "gpt_verdict": gpt[pid]["verdict"], "vb_call": v["pitch_call_code"],
                         "vb_count_before": f"{v['balls_before']}-{v['strikes_before']}", "match_status": st,
                         "naver_code": n.get("code", ""), "naver_word": n.get("word", ""), "naver_count_before": n.get("count_before", ""),
                         "naver_count_after": n.get("count_after", ""), "naver_next_count_before": nxt[0]["count_before"] if nxt else "",
                         "naver_verdict": verdict,
                         "vb_pa_sequence": " ".join(f"{r['pitch_number']}{r['pitch_call_code']}" for r in vb_pa),
                         "naver_pa_sequence": " ".join(f"{x['pitch_num']}{x['code']}" for x in pa)})
        print(game_id, "failed innings" if failed else "ok", failed, flush=True)
    with (RESULTS / "naver_queue_verify_2024_2026.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(dict(status), Counter((r["gpt_verdict"], r["naver_verdict"]) for r in rows))


def coverage() -> None:
    """2019-2023 KIA home games: does a pitch-level Naver relay exist? inning 1 for every game, full game for a sample."""
    out = {"definition": {"pitch_level": "inning 1 has pitch options with pitchNum and pitchResult",
                          "full_game_sample": "first KIA home game with a pitch-level inning 1 in each month, all innings"}, "seasons": {}}
    for season in range(2019, 2024):
        games = sorted(r["game_id"] for r in load_rows(ROOT, "games", season, columns=["game_id"]) if r["game_id"][10:12] == "HT")
        per_game, sampled_months, sample = {}, set(), {}
        for game_id in games:
            first = relay(game_id, 1)
            if first is None:
                per_game[game_id] = "no_relay"; continue
            opts = [o for pa in first.get("textRelays") or [] for o in pa.get("textOptions") or []]
            pitched = [o for o in opts if o.get("pitchNum") is not None and o.get("pitchResult") is not None]
            per_game[game_id] = "pitch_level" if pitched else ("text_only" if opts else "empty")
            if pitched and game_id[4:6] not in sampled_months:
                sampled_months.add(game_id[4:6]); pitches, failed = game_pitches(game_id)
                sample[game_id] = {"pitches": len(pitches), "failed_innings": failed, "codes": dict(Counter(p["code"] for p in pitches))}
        c = Counter(per_game.values())
        codes = Counter(); [codes.update(s["codes"]) for s in sample.values()]
        out["seasons"][str(season)] = {"kia_home_games": len(games), "status": dict(c), "not_pitch_level": sorted(g for g, v in per_game.items() if v != "pitch_level"),
                                       "full_game_sample": sample, "sample_W_per_game": round(codes["W"] / max(1, len(sample)), 2)}
        print(season, dict(c), "sample games", len(sample), "W", codes["W"], flush=True)
    (RESULTS / "naver_kia_home_coverage_2019_2023.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    {"queue": verify_queue, "coverage": coverage}[sys.argv[1]]()
