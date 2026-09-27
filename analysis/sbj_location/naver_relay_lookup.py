"""Normalize saved Naver relays and compare them with the investigated pitches.

Only reads ignored relay JSON and existing VB JSON. Writes analysis results only.
Run: python analysis/sbj_location/naver_relay_lookup.py
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path
import re
import statistics
import sys

from naver_relay_fetch import DEST, GAMES, ROOT

RES = ROOT / "analysis/sbj_location/results"
TM_TO_DISPLAY_OFFSET_KMH = -1.5
PTS = ("pitchId", "inn", "ballcount", "crossPlateX", "crossPlateY", "topSz", "bottomSz",
       "vy0", "vz0", "vx0", "z0", "y0", "x0", "ax", "ay", "az", "stance")
NUMERIC_VB = {"crossPlateX": "px", "topSz": "szTop", "bottomSz": "szBot", "vx0": "vx0",
              "vy0": "vy0", "vz0": "vz0", "x0": "x0", "y0": "y0", "z0": "z0",
              "ax": "ax", "ay": "ay", "az": "az"}
PITCH_WORD = re.compile("헛스윙|스트라이크|번트파울|파울|볼|타격|타구")
LABEL = re.compile(r"^(\d+)회(초|말)\s+([^()]+)\(([^)]+)\)")
VB_LABEL = re.compile(r"^(\d{3})-(\d{2})$")


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as out:
        writer = csv.DictWriter(out, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def number(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def key_inventory(value, prefix: str, fields: dict) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}"
            if path == "textOptions.text":
                example = "[중계 문장 저장 안 함]"
            elif isinstance(item, (dict, list)):
                example = f"{len(item)}개"
            else:
                example = str(item).replace("\n", " ")[:48]
            fields[path][type(item).__name__].add(example)
            if isinstance(item, (dict, list)):
                key_inventory(item, path, fields)
    elif isinstance(value, list):
        for item in value:
            key_inventory(item, prefix + "[]", fields)


def normalize():
    fields = defaultdict(lambda: defaultdict(set))
    rows, coverage, mismatch = [], [], []
    for game_id in GAMES:
        season = game_id[:4]
        folder = DEST / season / game_id
        files = sorted(folder.glob("inning_*.json"), key=lambda path: int(path.stem.split("_")[1]))
        expected = None
        for path in files:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            relay = payload["result"]["textRelayData"]
            if expected is None:
                expected = max(int(n) for side in relay["inningScore"].values() for n in side)
            names = {}
            for side in ("home", "away"):
                for group in ("Lineup", "Entry"):
                    for role in ("batter", "pitcher"):
                        for player in (relay.get(side + group) or {}).get(role) or []:
                            names[str(player.get("pcode"))] = player.get("name", "")
            pa_order = defaultdict(int)
            for pa in sorted(relay.get("textRelays") or [], key=lambda item: item.get("no", 0)):
                half = "top" if str(pa["homeOrAway"]) == "0" else "bottom"
                pitch_options = [option for option in pa.get("textOptions") or [] if option.get("ptsPitchId")]
                if pitch_options:
                    pa_order[half] += 1
                pts_by_id = defaultdict(list)
                for item in pa.get("ptsOptions") or []:
                    key_inventory(item, "ptsOptions", fields)
                    pts_by_id[str(item.get("pitchId"))].append(item)
                for option in pitch_options:
                    key_inventory(option, "textOptions", fields)
                    state = option.get("currentGameState") or {}
                    pid = str(option["ptsPitchId"])
                    pts = pts_by_id[pid].pop(0) if pts_by_id[pid] else {}
                    match = PITCH_WORD.search(str(option.get("text", "")))
                    row = {"game_id": game_id, "season": season, "inning": int(pa["inn"]),
                           "half": half, "pa_no": pa["no"], "pa_order_in_half": pa_order[half],
                           "pa_title": pa.get("title", ""),
                           "batter_id": str(state.get("batter", "")), "batter_name": names.get(str(state.get("batter")), ""),
                           "pitcher_id": str(state.get("pitcher", "")), "pitcher_name": names.get(str(state.get("pitcher")), ""),
                           "seqno": option.get("seqno"), "pitchNum": option.get("pitchNum"),
                           "ptsPitchId": pid, "pitchResult": option.get("pitchResult", ""),
                           "call_word": match.group(0) if match else "", "speed_kmh": option.get("speed", ""),
                           "pitch_type": option.get("stuff", ""), "ball_after": state.get("ball", ""),
                           "strike_after": state.get("strike", ""), "pts_present": bool(pts)}
                    row.update({key: pts.get(key) for key in PTS})
                    rows.append(row)
                    if not pts:
                        mismatch.append((game_id, path.name, pa.get("no"), pid, "text_without_pts"))
                for pid, unused in pts_by_id.items():
                    for _ in unused:
                        mismatch.append((game_id, path.name, pa.get("no"), pid, "pts_without_text"))
        present = {int(path.stem.split("_")[1]) for path in files}
        coverage.append((game_id, expected, len(present), sorted(set(range(1, (expected or 0) + 1)) - present)))
    columns = ["game_id", "season", "inning", "half", "pa_no", "pa_order_in_half", "pa_title", "batter_id", "batter_name",
               "pitcher_id", "pitcher_name", "seqno", "pitchNum", "ptsPitchId", "pitchResult", "call_word",
               "speed_kmh", "pitch_type", "ball_after", "strike_after", "pts_present"] + list(PTS)
    write_csv(RES / "naver_pitch_rows.csv", rows, columns)
    return rows, fields, coverage, mismatch


def vb_rows(game_id: str):
    season = game_id[:4]
    candidates = [ROOT / "data/raw" / season / f"{game_id}.json",
                  ROOT / "seasons" / season / "data/raw" / season / f"{game_id}.json"]
    path = next((path for path in candidates if path.exists()), None)
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    result = []
    pa_no = 0
    for block in payload["pbpData"]:
        for pa in block["pas"]:
            pa_no += 1
            for pitch_no, pitch in enumerate(pa["pitches"], 1):
                result.append({"inning": int(block["inning"]), "half": block["half"],
                               "batter_id": str(pa.get("batterId", "")), "pitcher_id": str(pa.get("pitcherId", "")),
                               "pitch_no": pitch_no, "label": f"{pa_no:03d}-{pitch_no:02d}", "pitch": pitch})
    return result


def call_code(known: str) -> str | None:
    if known.startswith("볼"):
        return "B"
    if known.startswith("파울") or known.startswith("번트 파울"):
        return "F"
    if known.startswith("헛스윙"):
        return "S"
    if known.startswith("스트라이크"):
        return "T"
    if known.startswith("타격"):
        return "H"
    return None


def expected_after(before: str, code: str | None):
    match = re.fullmatch(r"(\d)-(\d)", before)
    if not match or not code:
        return None
    balls, strikes = map(int, match.groups())
    if code == "B":
        balls += 1
    elif code in ("T", "S", "W"):
        strikes += 1
    elif code == "F":
        strikes = min(2, strikes + 1)
    return str(balls), str(strikes)


def candidate_for_target(target: dict, rows: list[dict]) -> tuple[list[dict], str]:
    source = target["source"]
    inning, half = target.get("inning"), target.get("half")
    if source == "captured":
        parsed = LABEL.match(target.get("pa_label", ""))
        if not parsed:
            return [], "타석 라벨 해석 실패"
        inning, half = parsed.group(1), "top" if parsed.group(2) == "초" else "bottom"
        batter, pitcher = parsed.group(3), parsed.group(4)
        candidates = [row for row in rows if row["game_id"] == target["game_id"] and
                      row["inning"] == int(inning) and row["half"] == half and
                      row["batter_name"] == batter and row["pitcher_name"] == pitcher and
                      str(row["pitchNum"]) == target["pitch_of_pa"]]
        code = call_code(target.get("known_call", ""))
        if code:
            candidates = [row for row in candidates if row["pitchResult"] == code]
        speed = number(target.get("known_speed_kmh"))
        if speed is not None:
            candidates = [row for row in candidates if number(row["speed_kmh"]) is not None and
                          abs(number(row["speed_kmh"]) - speed) <= 2]
        after = expected_after(target.get("count_before", ""), code)
        if after:
            candidates = [row for row in candidates if (str(row["ball_after"]), str(row["strike_after"])) == after]
        return candidates, f"캡처: {target['pa_label']} {target['pitch_of_pa']}구; 호출={code}; 구속={target.get('known_speed_kmh')}; 예상 뒤 카운트={after}"
    candidates = [row for row in rows if row["game_id"] == target["game_id"] and
                  row["inning"] == int(float(inning)) and row["half"] == half and
                  row["batter_id"] == target["batter_vb_id"] and
                  row["pitcher_id"] == target["pitcher_vb_id"] and
                  str(row["pitchNum"]) == target["pitch_of_pa"]]
    return candidates, f"TrackMan: 투수·타자 ID/반이닝/{target['pitch_of_pa']}구; TM−1.5km/h 기준 구속 ±3km/h 별도 대조; 카운트 연결 조건 아님"


def vb_presence(target: dict, rows: list[dict]) -> tuple[str, str]:
    if target["source"] != "half_short":
        return "not_applicable", ""
    structural = [row for row in rows if row["inning"] == int(float(target["inning"])) and
                  row["half"] == target["half"] and row["pitcher_id"] == target["pitcher_vb_id"] and
                  row["batter_id"] == target["batter_vb_id"] and str(row["pitch_no"]) == target["pitch_of_pa"]]
    speed = number(target.get("tm_speed_kmh"))
    candidates = (structural if speed is None else
                  [row for row in structural if number(row["pitch"].get("spd")) is not None and
                   abs(number(row["pitch"]["spd"]) - (speed + TM_TO_DISPLAY_OFFSET_KMH)) <= 3])
    status = ("yes" if len(candidates) == 1 else "ambiguous" if len(candidates) > 1 else
              "uncertain_speed_conflict" if structural else "no")
    return status, " / ".join(row["label"] for row in structural)


def lookup(rows: list[dict], vb: dict[str, list[dict]]):
    targets = list(csv.DictReader((RES / "missing_pitch_targets.csv").open(encoding="utf-8-sig")))
    result = []
    for index, target in enumerate(targets, 1):
        candidates, why = candidate_for_target(target, rows)
        status = ("ambiguous" if len(candidates) > 1 else "not_in_naver" if not candidates else
                  "found_with_location" if candidates[0]["pts_present"] and candidates[0]["crossPlateX"] is not None else
                  "found_no_location")
        row = candidates[0] if len(candidates) == 1 else {}
        present, vb_labels = vb_presence(target, vb[target["game_id"]])
        tm_speed = number(target.get("tm_speed_kmh"))
        naver_speed = number(row.get("speed_kmh"))
        speed_delta = naver_speed - tm_speed if tm_speed is not None and naver_speed is not None else None
        adjusted_delta = speed_delta - TM_TO_DISPLAY_OFFSET_KMH if speed_delta is not None else None
        count_after = expected_after(target.get("count_before", ""), row.get("pitchResult")) if row else None
        count_check = ("match" if count_after == (str(row["ball_after"]), str(row["strike_after"])) else
                       "mismatch") if count_after is not None else "unavailable"
        detail = (f"; 네이버−TrackMan 구속={speed_delta:+.3f}km/h; 기대 편차={adjusted_delta:+.3f}km/h; 카운트={count_check}"
                  if speed_delta is not None else f"; 카운트={count_check}")
        result.append({"target_row": index, "source": target["source"], "game_id": target["game_id"],
                       "inning": target["inning"] or (LABEL.match(target.get("pa_label", "")).group(1) if target["source"] == "captured" else ""),
                       "half": target["half"] or ("top" if "회초" in target.get("pa_label", "") else "bottom"),
                       "pa_label": target.get("pa_label", ""), "pitcher_id": target["pitcher_vb_id"],
                       "batter_id": target["batter_vb_id"], "pitch_of_pa": target["pitch_of_pa"],
                       "tm_pitch_no": target["tm_pitch_no"], "tm_speed_kmh": target["tm_speed_kmh"],
                       "tm_type": target["tm_type"], "known_call": target["known_call"],
                       "known_speed_kmh": target["known_speed_kmh"], "known_type": target["known_type"],
                       "count_before": target["count_before"], "classification": status,
                       "candidate_count": len(candidates), "candidate_pitch_ids": " / ".join(str(c["ptsPitchId"]) for c in candidates),
                       "naver_pitch_id": row.get("ptsPitchId", ""), "naver_pa_no": row.get("pa_no", ""),
                       "naver_pa_order_in_half": row.get("pa_order_in_half", ""),
                       "naver_pitch_num": row.get("pitchNum", ""), "naver_call": row.get("pitchResult", ""),
                       "naver_speed_kmh": row.get("speed_kmh", ""), "naver_count_after":
                       f"{row['ball_after']}-{row['strike_after']}" if row else "",
                       "naver_minus_tm_speed_kmh": round(speed_delta, 3) if speed_delta is not None else "",
                       "deviation_from_tm_minus_1_5_kmh": round(adjusted_delta, 3) if adjusted_delta is not None else "",
                       "speed_within_3kmh": abs(adjusted_delta) <= 3 if adjusted_delta is not None else "",
                       "count_check": count_check,
                       "crossPlateX": row.get("crossPlateX"), "crossPlateY": row.get("crossPlateY"),
                       "topSz": row.get("topSz"), "bottomSz": row.get("bottomSz"),
                       "trajectory_present": bool(row) and row.get("x0") is not None,
                       "vb_already_present": present, "vb_row_candidates": vb_labels, "evidence": why + detail})
        result[-1].update({key: row.get(key) for key in PTS})
    columns = list(result[0])
    write_csv(RES / "naver_pitch_lookup.csv", result, columns)
    return result


def trajectory_z(pts: dict, y: float) -> float | None:
    vals = [number(pts.get(key)) for key in ("y0", "vy0", "ay", "z0", "vz0", "az")]
    if any(value is None for value in vals):
        return None
    y0, vy, ay, z0, vz, az = vals
    disc = vy * vy - 2 * ay * (y0 - y)
    if disc < 0:
        return None
    times = [(-vy + sign * math.sqrt(disc)) / ay for sign in (-1, 1)] if ay else [(y-y0)/vy]
    t = min((t for t in times if t >= 0), default=None)
    return z0 + vz*t + 0.5*az*t*t if t is not None else None


def compare_confirmed(rows: list[dict], vb: dict[str, list[dict]]):
    by_game = defaultdict(list)
    for row in rows:
        by_game[row["game_id"]].append(row)
    diffs = defaultdict(list)
    large_px_games = Counter()
    verified, excluded = [], Counter()
    files = sorted(RES.glob("case*_correspondence.csv")) + [RES / "kim_lim_20250809_correspondence.csv"]
    for file in files:
        match = re.search(r"(20\d{6}[A-Z]{4}0)", file.name)
        game_id = match.group(1) if match else next(game for game in GAMES if game.startswith(file.name.split("_")[-2]))
        vb_by_label = {row["label"]: row for row in vb[game_id]}
        for item in csv.DictReader(file.open(encoding="utf-8-sig")):
            label = item.get("vb_row", "")
            if not item.get("mapping", "").startswith("확정") or not VB_LABEL.fullmatch(label):
                continue
            v = vb_by_label.get(label)
            if v is None:
                excluded["VB 행 없음"] += 1; continue
            pitch_no = number(item.get("real_pitch_no")) or number(item.get("naver_no"))
            if pitch_no is None:
                excluded["실제 투구 번호 없음"] += 1; continue
            candidates = [row for row in by_game[game_id] if row["inning"] == v["inning"] and row["half"] == v["half"] and
                          row["batter_id"] == v["batter_id"] and row["pitcher_id"] == v["pitcher_id"] and
                          row["pitchNum"] == int(pitch_no) and row["pts_present"]]
            known_speed = number(item.get("real_speed_kmh")) or number(item.get("naver_speed_kmh"))
            if known_speed is not None:
                candidates = [row for row in candidates if number(row["speed_kmh"]) is not None and
                              abs(number(row["speed_kmh"]) - known_speed) <= 2]
            ids = {row["ptsPitchId"] for row in candidates}
            if len(ids) != 1:
                excluded["네이버 ID 0개/여러 개"] += 1; continue
            n = candidates[0]
            verified.append((game_id, label, n["ptsPitchId"]))
            for nk, vk in NUMERIC_VB.items():
                a, b = number(n[nk]), number(v["pitch"].get(vk))
                if a is not None and b is not None:
                    diffs[nk + " − " + vk].append(a-b)
                    if nk == "crossPlateX" and abs(a-b) > .1:
                        large_px_games[game_id] += 1
            z = trajectory_z(n, 17/12)
            b = number(v["pitch"].get("pz"))
            if z is not None and b is not None:
                diffs["PTS trajectory z at y=17/12 − VB pz"].append(z-b)
    return verified, excluded, diffs, large_px_games


def report(rows, fields, coverage, mismatch, found, verified, excluded, diffs, large_px_games):
    lines = ["# 네이버 relay 투구 단위 조사", "", "## Q1. 위치·궤적", "",
             f"원문 {sum(p for _, _, p, _ in coverage)}이닝에서 문자 투구 {len(rows)}행을 읽었다. "
             f"`textOptions.ptsPitchId`와 `ptsOptions.pitchId`로 연결한 위치 행은 {sum(bool(r['pts_present']) for r in rows)}행이다. "
             "`ptsOptions`에는 `crossPlateX`, `crossPlateY`, `topSz`, `bottomSz`, "
             "`x0/y0/z0`, `vx0/vy0/vz0`, `ax/ay/az`가 있다. 직접적인 `crossPlateZ`/`pz` 필드는 없다.", "",
             "`crossPlateY`는 위치 좌표의 y 기준면 후보, `crossPlateX`는 그 면의 수평 좌표 후보이다. "
             "궤적 위치·존 높이의 단위는 feet, 속도는 ft/s, 가속도는 ft/s²로 보인다(VB 수치 및 운동학 대조에 근거한 추정). "
             "관측된 `y0`는 50 ft다. `crossPlateY`는 2020–2021년에 1.4167 ft(앞면 17/12 ft), "
             "2024–2026년에 0.7083 ft(중간면 8.5/12 ft)로, VB 시즌별 `px` 평면 규칙과 일치한다. "
             "`pz`에 해당하는 직접 필드는 없으며, 앞면 y=17/12 ft에서 궤적 z를 계산한 값만 비교했다. "
             "기준면·단위에 대한 API 공식 정의는 확인하지 못했다.", "",
             "## Q2. VB 원본과 같은 값인가", "",
             f"대응표의 `mapping`이 `확정`으로 시작하고 VB 단일 행과 네이버 단일 투구 ID가 연결된 {len(verified)}쌍을 비교했다. "
             f"제외 사유: {dict(excluded)}. 수평 위치 차이 절댓값 0.01 ft 이하는 "
             f"{sum(abs(x) <= .01 for x in diffs['crossPlateX − px'])}/{len(diffs['crossPlateX − px'])}쌍, "
             f"앞면 궤적 z와 VB `pz` 차이 0.01 ft 이하는 "
             f"{sum(abs(x) <= .01 for x in diffs['PTS trajectory z at y=17/12 − VB pz'])}/{len(diffs['PTS trajectory z at y=17/12 − VB pz'])}쌍이다. "
             f"수평 위치 차이 0.1 ft 초과는 {sum(large_px_games.values())}쌍({dict(large_px_games)})이다. "
             "일부 확정 투구의 위치·궤적은 크게 다르다. 네이버와 VB가 같은 공급원을 쓸 수 있으므로 일치해도 독립적인 위치 검증이 아니다.", "",
             "| 비교(네이버 − VB) | n | 중앙 절댓값 | 95백분위 절댓값 | 최대 절댓값 |", "|---|---:|---:|---:|---:|"]
    for name, values in diffs.items():
        absolute = sorted(abs(x) for x in values)
        p95 = absolute[min(len(absolute)-1, math.ceil(len(absolute)*.95)-1)]
        lines.append(f"| `{name}` | {len(values)} | {statistics.median(absolute):.5f} | {p95:.5f} | {max(absolute):.5f} |")
    groups = defaultdict(list)
    for row in rows:
        groups[(row["game_id"], row["ptsPitchId"])].append(row)
    dup = {key: value for key, value in groups.items() if len(value) > 1}
    same_pts = sum(all(item["pts_present"] for item in group) for group in dup.values())
    within_pa = sum(len({item["pa_no"] for item in group}) == 1 for group in dup.values())
    lines += ["", "## Q3. 복제·선행 기록과 투구 ID", "",
              f"동일 경기에서 문자 기록이 반복된 투구 ID는 {len(dup)}개다. 그중 {same_pts}개는 반복 행 모두 `ptsOptions` 기록도 있다. "
              f"동일 카드 안 반복 {within_pa}개, 카드 사이 반복 {len(dup) - within_pa}개다. "
              "대응표의 복제·선행 사례(채은성, 노진혁, 허경민, 정수빈, 박해민, 오스틴, 조수행, 김휘집 등)에서도 같은 ID가 반복된다. "
              "따라서 투구 ID는 중복을 묶는 단서지만 응답 전체의 `ptsOptions`가 공당 단 한 행은 아니다. "
              "같은 카드 안이나 복제 카드에 추적 행도 반복된다. UI 그림의 중복 제거 이유는 API만으로 확정할 수 없다.", "",
              "반례/주의: 2025-08-09 임지열은 현재 API에 같은 7개 ID를 담은 카드 두 장이 있다. "
              "기존 사용자 캡처의 7구 관찰과 카드 수가 다르므로 양쪽을 기록하며 어느 시점의 표시가 맞는지는 정하지 않는다.", "",
              "## 수집 범위", "", "| 경기 | 예상 이닝 | 성공 이닝 | 실패 이닝 |", "|---|---:|---:|---|"]
    for game, expected, present, missing in coverage:
        lines.append(f"| {game} | {expected} | {present} | {', '.join(map(str, missing)) or '없음'} |")
    counts = Counter((r["source"], r["classification"]) for r in found)
    lines += ["", f"## 대상 {len(found)}구 분류", "", "| 출처 | found_with_location | found_no_location | not_in_naver | ambiguous |",
              "|---|---:|---:|---:|---:|"]
    for source in ("captured", "half_short"):
        lines.append("| " + source + " | " + " | ".join(str(counts[source, status]) for status in
                     ("found_with_location", "found_no_location", "not_in_naver", "ambiguous")) + " |")
    ambiguous = [r for r in found if r["classification"] == "ambiguous"]
    lines += ["", "모호 후보: " + (", ".join(f"#{r['target_row']} {r['game_id']}" for r in ambiguous) if ambiguous else "없음") + "."]
    speed_bad = sum(r["source"] == "half_short" and r["speed_within_3kmh"] is False for r in found)
    speed_bad_rows = [r for r in found if r["source"] == "half_short" and r["speed_within_3kmh"] is False]
    count_good = sum(r["source"] == "half_short" and r["count_check"] == "match" for r in found)
    vb_count = Counter(r["vb_already_present"] for r in found if r["source"] == "half_short")
    lines += ["", f"`half_short` 단일 네이버 후보 중 TrackMan−1.5km/h 기준 편차가 ±3km/h를 넘는 행은 {speed_bad}건이다. "
              f"카운트 전이 일치 {count_good}건(독립 대조값, 연결 조건 아님). "
              f"VB 원본 별도 검사: {dict(vb_count)}.", "",
              "구속 충돌 대상: " + ", ".join(f"#{r['target_row']} {r['naver_pitch_id']}" for r in speed_bad_rows) + ".", "",
              "`half_short`에는 VB에 이미 있는 공도 포함된다. `vb_already_present`는 같은 반이닝·투수·타자·타석 내 순번과 "
              "TrackMan−1.5km/h 기준 구속 ±3km/h로 별도 검사한 결과다. 구조상 VB 후보는 있지만 속도가 어긋나면 `uncertain_speed_conflict`로 남긴다. "
              "네이버 단일 후보도 구속 차이를 별도 열에 기록하고, 카운트는 연결 조건에 쓰지 않았다. "
              "타석 분리·표시 구속 오류 때문에 유일한 구조 후보가 실제 같은 공임을 보장하지는 않는다.", "",
              f"문자·PTS 배열 불일치: {len(mismatch)}건 (`ptsPitchId=-1`인 문자 행은 위치 null).", "",
              "## 투구 항목의 실제 키·자료형·예시", "",
              "아래 목록은 받은 10경기의 투구 `textOptions`와 `ptsOptions`를 재귀적으로 조사했다. "
              "`textOptions.text`의 중계 문장 예시는 저장하지 않았다. 값은 길이를 제한한 예시다.", "",
              "| 경로 | 관측 자료형 | 예시 |", "|---|---|---|"]
    for path, types in sorted(fields.items()):
        examples = sorted({example for values in types.values() for example in values})
        example = examples[0] if examples else "null"
        example = example.replace("|", "\\|").replace("`", "'")
        lines.append(f"| `{path}` | {', '.join(sorted(types))} | `{example}` |")
    (RES / "naver_relay_fields.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    rows, fields, coverage, mismatch = normalize()
    vb = {game_id: vb_rows(game_id) for game_id in GAMES}
    found = lookup(rows, vb)
    verified, excluded, diffs, large_px_games = compare_confirmed(rows, vb)
    report(rows, fields, coverage, mismatch, found, verified, excluded, diffs, large_px_games)
    print("coverage", coverage)
    print("normalized", len(rows), "lookup", len(found), "classes", dict(Counter((r["source"], r["classification"]) for r in found)))
    print("confirmed Q2 pairs", len(verified), "excluded", dict(excluded))


def self_check():
    target = {"source": "half_short", "game_id": "G", "inning": "1", "half": "top",
              "batter_vb_id": "B", "pitcher_vb_id": "P", "pitch_of_pa": "1", "tm_speed_kmh": "140"}
    first = {"game_id": "G", "inning": 1, "half": "top", "batter_id": "B", "pitcher_id": "P",
             "pitchNum": 1, "speed_kmh": "140"}
    second = {**first, "speed_kmh": "133"}
    candidates, _ = candidate_for_target(target, [first, second])
    assert len(candidates) == 2, "a speed conflict must not silently select one of two records"
    assert vb_presence(target, [{"inning": 1, "half": "top", "batter_id": "B", "pitcher_id": "P",
                                 "pitch_no": 1, "label": "001-01", "pitch": {"spd": 133}}])[0] == "uncertain_speed_conflict"
    assert expected_after("1-2", "F") == ("1", "2")
    assert expected_after("1-2", "S") == ("1", "3")
    assert trajectory_z({"y0": 50, "vy0": -100, "ay": 0, "z0": 5, "vz0": 0, "az": 0}, 1) == 5
    print("self-check passed")


if __name__ == "__main__":
    self_check() if "--self-check" in sys.argv else main()
