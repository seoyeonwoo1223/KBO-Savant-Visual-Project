# Legacy VBA collector

This folder preserves the original desktop-Excel deliverables. They are not used by the GitHub Actions Python collector.

- `workbooks/` contains the untouched `.xlsx` source and macro-enabled `.xlsm` collector.
- `src/` contains the imported VBA modules.
- `scripts/` contains the local Excel COM runner and Windows scheduled-task installer.

Run the local collector with `powershell -File .\legacy\vba\scripts\Run_SwingTake_Update.ps1`. The workbook path is now resolved from `legacy/vba/workbooks/`.
