from __future__ import annotations

from pathlib import Path
import pyarrow.parquet as pq
import xlsxwriter


def export_latest(root: Path) -> Path:
    output = root / "exports" / "visualbaseball_savant_2026_latest.xlsx"; output.parent.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(output, {"strings_to_urls": False}); header = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#1F4E79", "align": "center"})
    for name in ("games", "events", "pitches"):
        path = root / "data" / "processed" / f"{name}.parquet"; rows = pq.read_table(path).to_pylist() if path.exists() else []
        sheet = workbook.add_worksheet(name.title()); sheet.freeze_panes(1, 0); sheet.hide_gridlines(2)
        columns = list(rows[0]) if rows else []
        for column, value in enumerate(columns):
            sheet.write(0, column, value, header)
            width = max([len(value)] + [len(str(row.get(value) or "")) for row in rows]) + 2
            sheet.set_column(column, column, min(48, max(12, width)))
        for row_index, row in enumerate(rows, 1):
            for column, value in enumerate(columns): sheet.write(row_index, column, row.get(value))
        if columns: sheet.autofilter(0, 0, max(1, len(rows)), len(columns) - 1)
    workbook.close(); return output
