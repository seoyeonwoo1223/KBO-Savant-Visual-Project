"""KBO 공식 포지션별 수비이닝을 아웃 수 단위로 저장합니다."""
from __future__ import annotations
import argparse
from html import unescape
import json
from pathlib import Path
import re
import requests
from refresh_leaderboard_running import FormParser, PREFIX

URL = "https://www.koreabaseball.com/Record/Player/Defense/Basic.aspx"
POSITIONS = {"투수": "P", "포수": "C", "1루수": "1B", "2루수": "2B", "3루수": "3B", "유격수": "SS", "좌익수": "LF", "중견수": "CF", "우익수": "RF"}


def innings_outs(text):
    text = text.strip()
    if text in {"1/3", "2/3"}:
        return int(text[0])
    match = re.fullmatch(r"(\d+)(?:\s+([12])/3)?", text.strip())
    if not match:
        raise ValueError(f"수비이닝 형식을 확인할 수 없습니다: {text}")
    return int(match[1]) * 3 + int(match[2] or 0)


def parse_page(text, season, allow_empty=False):
    form = FormParser()
    form.feed(text)
    for key, expected in [("ddlSeason$ddlSeason", str(season)), ("ddlSeries$ddlSeries", "0"), ("ddlPos$ddlPos", ""), ("ddlTeam$ddlTeam", "")]:
        if form.fields.get(PREFIX + key) != expected:
            raise ValueError("공식 수비 기록의 시즌·정규시즌·전체 포지션·팀 선택을 확인할 수 없습니다.")
    rows = []
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", text, re.S):
        player = re.search(r'playerId=(\d+)"[^>]*>([^<]+)', row)
        if not player:
            continue
        cells = dict(re.findall(r'<td\s+data-id="([^"]+)"[^>]*>(.*?)</td>', row, re.S))
        position = unescape(cells.get("POS_SC", "")).strip()
        if position not in POSITIONS or "DEFEN_INN2_CN" not in cells:
            raise ValueError("공식 수비 기록의 포지션·이닝 열 구조가 변경되었습니다.")
        rows.append({"player_id": player[1], "name": unescape(player[2]), "position": POSITIONS[position],
                     "outs": innings_outs(unescape(cells["DEFEN_INN2_CN"]))})
    if not rows and not allow_empty:
        raise ValueError("공식 수비 기록이 비었습니다.")
    return form.fields, rows


def refresh(root, season=2026):
    records = {}
    with requests.Session() as session:
        response = session.get(URL, timeout=30)
        response.raise_for_status()
        response.encoding = "utf-8"
        fields, rows = parse_page(response.text, season)
        for page in range(1, 101):
            for row in rows:
                key = (row["player_id"], row["position"])
                if key in records:
                    raise ValueError("공식 수비 기록의 선수·포지션이 중복되었습니다.")
                records[key] = row
            if len(rows) < 30:
                break
            fields[PREFIX + "hfPage"] = str(page + 1)
            fields["__EVENTTARGET"] = PREFIX + "lbtnOrderBy"
            fields["__EVENTARGUMENT"] = ""
            response = session.post(URL, data=fields, timeout=30)
            response.raise_for_status()
            response.encoding = "utf-8"
            fields, rows = parse_page(response.text, season, allow_empty=True)
            if not rows:
                visible_pages = [int(value) for value in re.findall(r'id="[^"]*ucPager_btnNo\d+"[^>]*>(\d+)</a>', response.text)]
                if not visible_pages or max(visible_pages) >= page + 1 or "DEFEN_INN2_CN" not in response.text:
                    raise ValueError("공식 수비 기록의 빈 페이지가 정상적인 목록 끝인지 확인할 수 없습니다.")
                break
        else:
            raise ValueError("공식 수비 기록 페이지 종료를 확인할 수 없습니다.")
    payload = {"season": season, "series": "regular", "source_url": URL,
               "period": "KBO 공식 페이지의 해당 시즌 현재 누적 수비이닝 (PBP 기준일과 다를 수 있음)",
               "records": [records[key] for key in sorted(records)]}
    path = root / "data/leaderboards/source" / f"{season}_fielding.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"공식 수비 {season}: {len(records)}개 선수·포지션")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--season", type=int, default=2026)
    args = parser.parse_args()
    refresh(args.root, args.season)
