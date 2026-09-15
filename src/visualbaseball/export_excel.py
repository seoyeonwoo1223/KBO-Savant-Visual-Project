from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import xlsxwriter

from .curated import load_rows


def export_latest(root: Path, season: int = 2026) -> Path:
    """Publish only source tables; decision output stays in Parquet and profile JSON."""
    output = root / "exports" / f"visualbaseball_savant_{season}_latest.xlsx"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".xlsx.tmp")
    workbook = xlsxwriter.Workbook(temporary, {"strings_to_urls": False})
    workbook.set_properties({"created": datetime(2026, 1, 1, tzinfo=timezone.utc)})
    header = workbook.add_format(
        {"bold": True, "font_color": "#FFFFFF", "bg_color": "#1F4E79", "align": "center"}
    )

    for name in ("games", "events", "pitches"):
        write_sheet(workbook, header, name.title(), load_rows(root, name, season))
    workbook.close()
    temporary.replace(output)
    return output


def write_sheet(workbook, header, title, rows):
    """One frozen, filtered, width-fitted sheet. Shared by every export here."""
    sheet = workbook.add_worksheet(title)
    sheet.freeze_panes(1, 0)
    sheet.hide_gridlines(2)
    columns = list(rows[0]) if rows else []
    for column, value in enumerate(columns):
        sheet.write(0, column, value, header)
        width = max([len(value)] + [len(str(row.get(value) or "")) for row in rows]) + 2
        sheet.set_column(column, column, min(48, max(12, width)))
    for row_index, row in enumerate(rows, 1):
        for column, value in enumerate(columns):
            sheet.write(row_index, column, row.get(value))
    if columns:
        sheet.autofilter(0, 0, max(1, len(rows)), len(columns) - 1)
    return sheet


def _workbook(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".xlsx.tmp")
    workbook = xlsxwriter.Workbook(temporary, {"strings_to_urls": False})
    # A fixed creation time keeps a rerun with identical content byte-identical,
    # so the workflow's empty-diff guard still works.
    workbook.set_properties({"created": datetime(2026, 1, 1, tzinfo=timezone.utc)})
    header = workbook.add_format(
        {"bold": True, "font_color": "#FFFFFF", "bg_color": "#1F4E79", "align": "center"}
    )
    return workbook, header, temporary


def export_plate_judgment(root: Path, season: int, sheets: dict) -> Path:
    """Task 4 / 5 deliverable: per-batter metrics, denominators, missing reasons."""
    output = root / "exports" / f"plate_judgment_{season}.xlsx"
    workbook, header, temporary = _workbook(output)
    for title, rows in sheets.items():
        write_sheet(workbook, header, title, rows)
    workbook.close()
    temporary.replace(output)
    return output
