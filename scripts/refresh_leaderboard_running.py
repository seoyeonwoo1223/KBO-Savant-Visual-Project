"""KBO 공식 정규시즌 주루 기록을 시즌·공식 선수 ID로 저장합니다."""
from __future__ import annotations
import argparse
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import requests

URL = "https://www.koreabaseball.com/Record/Player/Runner/Basic.aspx"
PREFIX = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$"

class FormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fields = {}
        self.select = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and attrs.get("name"):
            self.fields[attrs["name"]] = attrs.get("value", "")
        if tag == "select":
            self.select = attrs.get("name")
            self.fields[self.select] = ""
        if tag == "option" and self.select and "selected" in attrs:
            self.fields[self.select] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "select":
            self.select = None


def parse_page(text, season):
    form = FormParser()
    form.feed(text)
    if form.fields.get(PREFIX + "ddlSeason$ddlSeason") != str(season) or form.fields.get(PREFIX + "ddlSeries$ddlSeries") != "0":
        raise ValueError("공식 주루 기록의 시즌·정규시즌 선택을 확인할 수 없습니다.")
    rows = []
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", text, re.S):
        player = re.search(r'playerId=(\d+)"[^>]*>([^<]+)', row)
        if not player:
            continue
        cells = re.findall(r'<td\b[^>]*>(.*?)</td>', row, re.S)
        values = {key: int(value) for key, value in re.findall(r'<td data-id="(SB_CN|CS_CN|GAME_CN)"[^>]*>(\d+)</td>', row)}
        if set(values) != {"SB_CN", "CS_CN", "GAME_CN"}:
            raise ValueError("공식 주루 기록의 열 구조가 변경되었습니다.")
        rows.append({"player_id": player[1], "name": unescape(player[2]), "team": unescape(cells[2]).strip(),
                     "SB": values["SB_CN"], "CS": values["CS_CN"], "G": values["GAME_CN"]})
    if not rows:
        raise ValueError("공식 주루 기록이 비었습니다.")
    return form.fields, rows


def refresh(root, season=2026):
    with requests.Session() as session:
        response = session.get(URL, timeout=30)
        response.raise_for_status()
        response.encoding = "utf-8"
        fields, rows = parse_page(response.text, season)
        players = {row["player_id"]: row for row in rows}
        for page in range(2, 31):
            if len(rows) < 30:
                break
            fields[PREFIX + "hfPage"] = str(page)
            fields["__EVENTTARGET"] = PREFIX + "lbtnOrderBy"
            fields["__EVENTARGUMENT"] = ""
            response = session.post(URL, data=fields, timeout=30)
            response.raise_for_status()
            response.encoding = "utf-8"
            fields, rows = parse_page(response.text, season)
            new = {row["player_id"]: row for row in rows if row["player_id"] not in players}
            if len(new) != len(rows):
                raise ValueError("공식 주루 페이지가 중복되어 전체 집계를 확인할 수 없습니다.")
            players.update(new)
        else:
            raise ValueError("공식 주루 기록 페이지 종료를 확인할 수 없습니다.")
    payload = {"season": season, "series": "regular", "source_url": URL,
               "period": "KBO 공식 페이지의 해당 시즌 현재 누적값 (PBP 기준일과 다를 수 있음)",
               "players": sorted(players.values(), key=lambda row: row["player_id"])}
    path = root / "data/leaderboards/source" / f"{season}_running.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"공식 주루 {season}: {len(players)}명")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--season", type=int, default=2026)
    args = parser.parse_args()
    refresh(args.root, args.season)
