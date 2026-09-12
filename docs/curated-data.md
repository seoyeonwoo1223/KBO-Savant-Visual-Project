# Canonical pitch data

The production flow is `raw -> curated Parquet -> metric`.

## Storage contract

- Raw Visual Baseball responses remain at `data/raw/<season>/<game_id>.json` (2025 uses its existing `seasons/2025` storage root).
- Canonical tables use monthly Parquet partitions at `data/curated/{pitches,events,games}/season=<year>/month=MM.parquet`. `partition-index.json` maps each game to its month and table hashes: targeted game reads open only that month; build planning does not enumerate Parquet files. Migrate an existing game-shard season with `python -m visualbaseball.compact_curated --season YYYY`.
- `data/curated/sources/season=<year>/<game_id>.json` records first/last collection and check times, revision, observed y0, row reconciliation, provenance, and `raw_sha256`, `pitch_sha256`, `schema_sha256`.
- Before an existing raw file changes, `data/curated/audit/season=<year>/<game_id>.jsonl` receives both raw hashes, pitch counts, and changed field paths. Raw history is not duplicated.
- Metric-owned results live below `data/metrics/<metric>/<season>/`. Excel and web JSON remain publication outputs only. `data/metrics/_state/<season>/` stores independent input/code hashes for each production metric; unchanged metrics are skipped.

`pitch_id` retains the existing stable `game_id + plate-appearance sequence + pitch number` identity. A provider field unrelated to parsed game/event/pitch values therefore changes `raw_sha256` but not `pitch_sha256`, and does not rewrite the shard.

## Coordinates and nulls

Raw `relH` remains `release_height_cm`; raw `y0` remains `y0` and is also exposed as `source_y0`. Constant-acceleration kinematics produce:

- `release_x_50`, `release_z_50`, `release_x_55`, `release_z_55`: centimetres at the named y plane.
- `vx_50`, `vy_50`, `vz_50`, `vx_55`, `vy_55`, `vz_55`: feet/second.
- `plate_x_error_cm`, `plate_z_error_cm`: raw `time` reconstruction minus raw `px/pz`.
- `relh_minus_z50_cm`: raw `relH` minus normalized 50 ft z.

`trajectory_status=valid` requires complete finite trajectory fields, y0 of 50 or 55 ft, and real 50/55 ft solutions within one second. Missing, unsolved, and unexpected-y0 rows remain in curated data with null derived values. Dataset-level acceptance is median absolute plate error below 1 cm and p95 below 2 cm on each axis; this does not delete an individual pitch.

The 2022-2024 workbooks have no retained raw JSON or y0 column. Their one-time migration records `legacy_excel_one_time_conversion`, the workbook hash, `raw_available=false`, and the documented assumption that historical x0/z0 is the 50 ft plane. This provenance is not presented as a raw hash.

## Commands

```powershell
$env:PYTHONPATH = "src"
python -m visualbaseball.build_curated --season 2026 --validate
python -m visualbaseball.build_curated --season 2025 --storage-root seasons/2025 --validate
python -m visualbaseball.build_curated --season 2024 --validate
python -m visualbaseball.cli --collection-mode recent
python -m visualbaseball.cli --collection-mode sample --auto-reconcile
python -m visualbaseball.cli --collection-mode reconcile --refresh-workers 3
```

`recent` checks new/failed/incomplete work and completed games in the latest seven days. `sample` deterministically selects eight completed games older than 30 days across the season. A sample y0/schema change or analysis-hash changes in at least two games warns, or expands to full reconcile with `--auto-reconcile`. Migration writes all new monthly partitions and its index before deleting legacy files, so rerunning after interruption is safe. A missing compact partition fails closed; restore it by rebuilding that season from retained raw data rather than publishing a partial month.
