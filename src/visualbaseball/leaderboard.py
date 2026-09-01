"""Normalize user-supplied KBO leaderboard workbooks for the static site."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pandas as pd


SHEET_META = {
    "기본-타자": ("batting", "기본"),
    "확장-타자": ("batting-advanced", "확장"),
    "수비-타자": ("fielding", "수비"),
    "기본-투수": ("pitching", "기본"),
    "확장-투수": ("pitching-advanced", "확장"),
    "투구-투수": ("pitch-value", "구종 가치"),
}

HEADER_LABELS = {
    "RK": "순위", "rk": "순위", "Player": "선수", "Pos": "포지션",
    "Team": "팀", "Year": "연도", "Runs Prevented": "Runs Prevented",
}

PLAYER_NAME_FIXES = {"오태콘": "오태곤"}


def _clean_header(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value)).strip()
    return re.sub(r"\.\d+$", "", text)


def _json_value(value: object) -> object:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return round(value, 6)
    return value


def _columns(frame: pd.DataFrame, sheet: str) -> list[dict[str, str]]:
    seen: dict[str, int] = {}
    result = []
    for raw in frame.columns:
        base = _clean_header(raw)
        seen[base] = seen.get(base, 0) + 1
        key = base if seen[base] == 1 else f"{base}_{seen[base]}"
        label = HEADER_LABELS.get(base, base)
        if sheet == "수비-타자" and seen[base] > 1:
            label = f"{base} 수비이닝"
        elif sheet == "수비-타자" and base in {"1B", "2B", "3B", "SS", "LF", "CF", "RF"}:
            label = f"{base} OAA"
        elif sheet == "투구-투수" and base == "Run Value":
            label = "Run Value"
        result.append({"key": key, "label": label})
    return result


def workbook_payload(path: Path) -> dict:
    book = pd.ExcelFile(path)
    datasets = []
    for sheet, (dataset_id, title) in SHEET_META.items():
        source_sheet = "수비" if sheet == "수비-타자" and "수비" in book.sheet_names else sheet
        if source_sheet not in book.sheet_names:
            continue
        frame = pd.read_excel(path, sheet_name=source_sheet)
        frame = frame.dropna(axis=0, how="all").dropna(axis=1, how="all")
        if frame.empty:
            continue
        columns = _columns(frame, sheet)
        rows = []
        for values in frame.itertuples(index=False, name=None):
            row = {column["key"]: _json_value(value) for column, value in zip(columns, values)}
            row["Player"] = PLAYER_NAME_FIXES.get(row.get("Player"), row.get("Player"))
            if row.get("Player"):
                rows.append(row)
        datasets.append({"id": dataset_id, "title": title, "columns": columns, "rows": rows})
    years = sorted({int(row["Year"]) for data in datasets for row in data["rows"] if row.get("Year")})
    if len(years) != 1:
        raise ValueError(f"Expected one season in {path.name}; found {years}")
    return {"schema_version": 1, "season": years[0], "datasets": datasets}


def build_leaderboards(inputs: list[Path], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    seasons = []
    availability = {}
    for path in inputs:
        payload = workbook_payload(path)
        season = payload["season"]
        seasons.append(season)
        availability[str(season)] = [item["id"] for item in payload["datasets"]]
        (output / f"{season}.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
    catalog = {"schema_version": 1, "seasons": sorted(seasons, reverse=True), "availability": availability}
    (output / "index.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
