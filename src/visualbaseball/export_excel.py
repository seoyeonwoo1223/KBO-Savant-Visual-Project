from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq
import xlsxwriter


def export_latest(root: Path, season: int = 2026, source_root: Path | None = None) -> Path:
    """Publish only source tables; decision output stays in Parquet and profile JSON."""
    source_root = source_root or root
    output = root / "exports" / f"visualbaseball_savant_{season}_latest.xlsx"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".xlsx.tmp")
    workbook = xlsxwriter.Workbook(temporary, {"strings_to_urls": False})
    # A stable core timestamp prevents a no-change scheduled run from creating
    # a byte-different workbook and an unnecessary profile commit.
    workbook.set_properties({"created": datetime(2026, 1, 1, tzinfo=timezone.utc)})
    header = workbook.add_format(
        {"bold": True, "font_color": "#FFFFFF", "bg_color": "#1F4E79", "align": "center"}
    )

    # "decision_pitches" duplicates the full pitch table and is deliberately
    # not published in Excel: it is a derived analysis artifact, not source data.
    for name in ("games", "events", "pitches"):
        path = source_root / "data" / "processed" / f"{name}.parquet"
        rows = pq.read_table(path).to_pylist() if path.exists() else []
        sheet = workbook.add_worksheet(name.title())
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
    workbook.close()
    temporary.replace(output)
    return output
