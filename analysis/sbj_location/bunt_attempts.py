"""Audit observed bunt pitches in cached 2025–2026 Naver relays.

Run with PYTHONPATH=src: python analysis/sbj_location/bunt_attempts.py [seasons...]   (default 2025 2026)
With seasons given, only those seasons' rows are rebuilt; rows of the other seasons stay as the existing CSV has them.
Only compact bunt words, never full relay sentences, enter tracked outputs.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import re
import sys

from bunt_relay_fetch import SEASONS, games, relay_at, seasons_from_argv
from naver_relay_location_fetch import DEST, ROOT

sys.path.insert(0, str(ROOT / "src"))
from visualbaseball.curated import load_rows

RESULT = ROOT / "analysis/sbj_location/results"
WORDS = re.compile(r"(?:희생\s*|기습\s*|스퀴즈\s*|쓰리\s*)?번트(?:\s*(?:파울|헛스윙|안타|아웃))?")
COLUMNS = ("season", "game_id", "pitch_id", "naver_pitch_id", "naver_code",
           "naver_phrase", "vb_call", "vb_count_before", "naver_count_after", "match_status")


def phrase(text: object) -> str:
    return " / ".join(dict.fromkeys(x.replace(" ", "") for x in WORDS.findall(str(text or ""))))


def observed(relay: dict) -> list[dict]:
    found = []
    for pa in relay.get("textRelays") or []:
        options = sorted(pa.get("textOptions") or [], key=lambda item: int(item.get("seqno") or 0))
        pitches = [item for item in options if item.get("pitchResult") is not None and item.get("pitchNum") is not None]
        def identity(item):
            pid = str(item.get("ptsPitchId") or "")
            return pid if pid not in {"", "-1", "0"} else f"missing:{pa.get('inn')}:{pa.get('no')}:{item.get('seqno')}"
        bunt_by_pitch = defaultdict(set)
        for option in options:
            word = phrase(option.get("text"))
            if not word:
                continue
            if option in pitches:
                bunt_by_pitch[identity(option)].update(word.split(" / "))
            else:
                # A bunt PA result follows the batted pitch or third bunt foul.
                prior = [p for p in pitches if int(p.get("seqno") or 0) < int(option.get("seqno") or 0)]
                if prior and str(prior[-1].get("pitchResult")) in {"H", "X", "W"}:
                    bunt_by_pitch[identity(prior[-1])].update(word.split(" / "))
        for option in pitches:
            key = identity(option)
            if key not in bunt_by_pitch:
                continue
            pid = str(option.get("ptsPitchId") or "")
            state = option.get("currentGameState") or {}
            found.append({"inning": int(pa["inn"]),
                          "half": "top" if str(pa["homeOrAway"]) == "0" else "bottom",
                          "pitcher_id": str(state.get("pitcher") or ""),
                          "batter_id": str(state.get("batter") or ""),
                          "pitch_num": int(option["pitchNum"]),
                          "speed": option.get("speed"),
                          "naver_pitch_id": pid if pid not in {"-1", "0"} else "",
                          "source_key": key,
                          "naver_code": str(option.get("pitchResult") or ""),
                          "naver_phrase": " / ".join(sorted(bunt_by_pitch[key])),
                          "naver_count_after": f"{state.get('ball', '')}-{state.get('strike', '')}"})
    return found


def match(row: dict, by_id: dict, by_context: dict) -> tuple[str, dict | None]:
    direct = by_id.get((row["game_id"], row["naver_pitch_id"]), [])
    if direct:
        return ("matched_id", direct[0]) if len(direct) == 1 else ("ambiguous", None)
    key = (row["game_id"], row["inning"], row["half"], row["pitcher_id"],
           row["batter_id"], row["pitch_num"])
    try:
        speed = float(row["speed"])
    except (TypeError, ValueError):
        return "unmatched", None
    candidates = [candidate for candidate in by_context.get(key, [])
                  if candidate.get("velocity_kmh") is not None
                  and abs(float(candidate["velocity_kmh"]) - speed) <= 1]
    return (("matched_context", candidates[0]) if len(candidates) == 1 else
            ("ambiguous", None) if candidates else ("unmatched", None))


def main() -> None:
    seasons = seasons_from_argv()
    all_games = games(seasons)
    columns = ["pitch_id", "game_id", "inning", "inning_half", "pitcher_id", "batter_id",
               "pitch_number", "velocity_kmh", "naver_pitch_id", "pitch_call_code",
               "balls_before", "strikes_before"]
    by_id, by_context = defaultdict(list), defaultdict(list)
    for season in seasons:
        for pitch in load_rows(ROOT, "pitches", season, columns=columns):
            if pitch.get("naver_pitch_id"):
                by_id[(pitch["game_id"], str(pitch["naver_pitch_id"]))].append(pitch)
            key = (pitch["game_id"], int(pitch["inning"]), pitch["inning_half"],
                   str(pitch["pitcher_id"]), str(pitch["batter_id"]), int(pitch["pitch_number"]))
            by_context[key].append(pitch)
    rows, failed, coverage = [], [], Counter()
    codes = defaultdict(Counter)
    seen = {}
    for game_id in all_games:
        folder = DEST / game_id[:4] / game_id
        first = relay_at(folder / "inning_1.json")
        if first is None:
            failed.append((game_id, "inning_1"))
            continue
        try:
            expected = max(int(n) for side in (first.get("inningScore") or {}).values()
                           for n in side if str(n).isdigit())
        except ValueError:
            failed.append((game_id, "inningScore"))
            continue
        for inning in range(1, expected + 1):
            relay = relay_at(folder / f"inning_{inning}.json")
            if relay is None:
                failed.append((game_id, f"inning_{inning}"))
                continue
            coverage[game_id[:4]] += 1
            for item in observed(relay):
                item.update(game_id=game_id, season=int(game_id[:4]))
                dedupe = (game_id, item["source_key"])
                if dedupe in seen:
                    if (seen[dedupe]["naver_code"], seen[dedupe]["naver_phrase"]) != (item["naver_code"], item["naver_phrase"]):
                        seen[dedupe]["match_status"] = "ambiguous"
                        for field in ("pitch_id", "vb_call", "vb_count_before"):
                            seen[dedupe][field] = ""
                    continue
                status, vb = match(item, by_id, by_context)
                output = {"season": item["season"], "game_id": game_id,
                          "pitch_id": vb["pitch_id"] if vb else "",
                          "naver_pitch_id": item["naver_pitch_id"],
                          "naver_code": item["naver_code"], "naver_phrase": item["naver_phrase"],
                          "vb_call": vb["pitch_call_code"] if vb else "",
                          "vb_count_before": f"{vb['balls_before']}-{vb['strikes_before']}" if vb else "",
                          "naver_count_after": item["naver_count_after"], "match_status": status}
                rows.append(output)
                seen[dedupe] = output
                codes[item["naver_code"]][item["naver_phrase"]] += 1
    RESULT.mkdir(parents=True, exist_ok=True)
    path = RESULT / "bunt_attempts_2025_2026.csv"
    kept = []
    if set(seasons) != set(SEASONS) and path.exists():
        with path.open(encoding="utf-8-sig", newline="") as stream:
            kept = [r for r in csv.DictReader(stream) if int(r["season"]) not in seasons]
    rows = [{**r, "season": int(r["season"])} for r in kept] + rows
    codes = defaultdict(Counter)
    for r in rows:
        codes[r["naver_code"]][r["naver_phrase"]] += 1
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: (row["game_id"], row["naver_pitch_id"])))
    out = ["# 2025–2026 네이버 번트 시도 전수 조사", "", "네이버 문구에 `번트`가 나타난 투구와 번트 결과의 마지막 투구를 센다. 타석 결과 줄의 번트는 같은 카드에서 직전 `H`/`X`/`W` 투구에 연결한 추정이다. 중계 문구에 번트가 없으면 검출할 수 없다. 같은 투구 ID의 반복 카드는 한 공으로 센다. 네이버와 VB는 공급원을 공유할 수 있다.", "", "## 관측 코드·문구", "", "| 코드 | 번트 문구 | 공 |", "|---|---|---:|"]
    for code, phrases in sorted(codes.items()):
        for word, count in sorted(phrases.items()):
            out.append(f"| `{code}` | {word} | {count} |")
    out += ["", "## 시즌별 코드 × VB 호출", "", "| 시즌 | 네이버 코드 | VB 호출 | 공 |", "|---:|---|---|---:|"]
    cross = Counter((r["season"], r["naver_code"], r["vb_call"] or "미대응") for r in rows)
    for key, count in sorted(cross.items()):
        out.append(f"| {key[0]} | `{key[1]}` | `{key[2]}` | {count} |")
    out += ["", "## 집계", ""]
    for season in SEASONS:
        subset = [r for r in rows if r["season"] == season]
        bunt_foul_b = sum(r["naver_code"] == "W" and r["vb_call"] == "B" for r in subset)
        if season not in seasons:
            out.append(f"- {season}: 이번 실행에서 다시 수집하지 않음(기존 CSV 행 유지), 번트 시도 {len(subset)}구, VB `B` {sum(r['vb_call'] == 'B' for r in subset)}구, 네이버 `W`·VB `B` {bunt_foul_b}구")
            continue
        out.append(f"- {season}: 경기 {sum(game_id.startswith(str(season)) for game_id in all_games)}개, 성공 이닝 {coverage[str(season)]}개, 번트 시도 {len(subset)}구, VB `B` {sum(r['vb_call'] == 'B' for r in subset)}구, 네이버 `W`·VB `B` {bunt_foul_b}구")
    statuses = Counter(r["match_status"] for r in rows)
    out += [f"- 대응 상태: {dict(sorted(statuses.items()))}; ambiguous {statuses['ambiguous']}구, unmatched {statuses['unmatched']}구", "", "## 대응 실패", ""]
    for row in rows:
        if row["match_status"] in {"ambiguous", "unmatched"}:
            out.append(f"- {row['game_id']} {row['naver_pitch_id']}: {row['match_status']}")
    if not any(r["match_status"] in {"ambiguous", "unmatched"} for r in rows):
        out.append("- 없음")
    out += ["", "## 수집 실패 경기·이닝", ""]
    out += [f"- {game_id} {inning}" for game_id, inning in failed] or ["- 없음"]
    (RESULT / "bunt_attempts_summary.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"games={len(all_games)} innings={dict(coverage)} bunt_rows={len(rows)} statuses={dict(statuses)} failed_innings={len(failed)}")
    if failed:
        raise SystemExit("relay coverage is incomplete; rerun fetch then this audit")


if __name__ == "__main__":
    main()
