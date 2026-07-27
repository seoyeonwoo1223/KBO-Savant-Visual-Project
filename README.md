# Visual Baseball incremental collector

## Delivery status

The collector is integrated into `visualbaseball_savant_2026_incremental.xlsm`. Excel COM and programmatic VBA-project access were verified, all source modules were imported, initialization and VBE compilation passed, and the saved workbook was closed and reopened successfully. The original `.xlsx` remains unchanged.

## Confirmed public requests

Confirmed from the site's current page resources and same-origin requests on 2026-07-27:

| Purpose | Request |
|---|---|
| Season schedule | `GET https://visualbaseball.com/api/schedule/season?y=2026` |
| Date schedule | `GET https://visualbaseball.com/api/schedule/date?d=YYYY-MM-DD` |
| Game PBP | `GET https://visualbaseball.com/api/game/pbp?id=GAME_ID` |
| Game pitching view | `GET https://visualbaseball.com/api/game/pitches?id=GAME_ID` |
| Game records | `GET https://visualbaseball.com/api/game/records?id=GAME_ID` |

The collector uses the season schedule and game PBP requests. The PBP response already contains the ordered half-innings, plate appearances, pitches, substitutions, and PA-boundary base snapshots needed by this implementation.

The public request flow is:

1. Load `/schedule`.
2. Retain the returned session cookies.
3. Read the `api-token` meta value from that page.
4. Send it as `X-Api-Token` on same-origin API GET requests.

This is the same public flow used by the frontend. The collector does not bypass authentication, CAPTCHA, access controls, or rate limits.

## Response mapping

| Existing workbook | Response field | Incremental field |
|---|---|---|
| `Date`, `Game ID`, `Stadium` | schedule `gameId/stadium`; `gameData` | `game_date`, `game_id`, `stadium` |
| `Pitcher`, `Batter`, IDs | `pbpData[].pas[]` | pitcher/batter ID and name |
| `Game Pitch #`, `Pitch`, `PA`, `Inn.`, `Half` | array order plus inning/half | `event_seq`, `pitch_number`, `pa_id`, `inning`, `inning_half` |
| `Result`, `PA Result`, `Pitch Call Code` | pitch `r`; PA `result/type` | `pitch_result`, `pa_result`, `pitch_call_code` |
| type, velocity, location, trajectory, movement | pitch `stuff/spd/px/pz/...` | normalized fields plus retained useful legacy fields |
| not present | PA `basesBefore/basesAfter`, `outsAfter`, half `scoreAfter` | before/after count, outs, bases, score, and state codes |
| not present | `subs[]` and source snapshot differences | `Events` rows and `parse_status` |

The original source workbook has `Savant`, `README`, and `LegacyRaw`. Initialization renames `Savant` to `Pitches`, removes the excluded source column at position 11 after checking its neighboring headers, and adds the normalized fields.

## State encoding

- Base code is an integer from 0 through 7.
- First base adds 1, second base adds 2, and third base adds 4.
- RE24 state code is `base_code * 3 + outs`, producing identifiers 0 through 23.
- RE288 state code is `((RE24_state * 4 + balls) * 3 + strikes)`, producing identifiers 0 through 287.
- These are state identifiers only. No expectancy or run-value values are calculated.

Pitch call codes are `B` ball, `F` foul, `S` swinging strike, `T` called strike, and `X` ball in play. A two-strike foul leaves the strike count at two. The terminal pitch receives the completed PA base, out, and score state.

## Source limitation

The public PBP response does not expose every non-pitch runner action as an original event code and description. It exposes substitutions and PA-boundary base snapshots. When a snapshot changes without an exposed event, the collector stores a `state_adjustment` event with `parse_status=unknown`; it does not invent an original code or description.

Because the source does not expose runner state between individual pitches, games requiring an unexposed mid-PA runner action cannot be proven to the full requested event-level standard. Treat this as a collection-source limitation, not as confirmed complete state reconstruction.

## Files

- `src_vba/JsonConverter.bas` — VBA-JSON v2.3.1, MIT licensed; adjusted to use late-bound `Scripting.Dictionary` so no reference must be enabled.
- `src_vba/LICENSE-VBA-JSON.txt` — upstream MIT license.
- `src_vba/modMain.bas` — `InitializeIncrementalWorkbook` and `RunIncrementalUpdate`.
- `src_vba/modConfig.bas` — configuration.
- `src_vba/modHttp.bas` — UTF-8 HTTP, public session bootstrap, retries, delay, and status checks.
- `src_vba/modCollector.bas` — incremental candidate selection and per-game transaction boundary.
- `src_vba/modParser.bas` — PBP parsing and normalized rows.
- `src_vba/modStateMachine.bas` — count, outs, bases, score, and state codes.
- `src_vba/modCache.bas` — pending/final raw files and update lock.
- `src_vba/modExcelWriter.bas` — sheets, headers, replacement, and append operations.
- `src_vba/modValidation.bas` — final-game gates.
- `src_vba/modLogger.bas` — `Update_Log` rows.
- `src_vba/modUtils.bas` — safe conversion, UTF-8 files, delay, paths, and SHA-256 file hashing.
- `Run_SwingTake_Update.ps1` — Excel COM runner with cleanup and meaningful exit code.
- `Install_SwingTake_Schedule.ps1` — daily local-noon scheduled task installer.

## Workbook integration

The delivered `.xlsm` was created through Excel COM with file format 52; it is not an extension rename. These are the reproducible rebuild steps:

1. Open the provided `visualbaseball_savant_2026.xlsx` in desktop Excel.
2. Use **Save As** and create `visualbaseball_savant_2026_incremental.xlsm` in this folder. Do not overwrite the `.xlsx`.
3. Press `Alt+F11` to open the Visual Basic Editor.
4. Select the new workbook project.
5. Use **File > Import File** and import every `.bas` file in `src_vba`. Import `JsonConverter.bas` first.
6. Run `InitializeIncrementalWorkbook` once.
7. Save, close, and reopen the workbook. Confirm that the sheets are `Config`, `Games`, `Events`, `Pitches`, `Update_Log`, `README`, and `LegacyRaw`.

The required entry point is:

```vba
Public Sub RunIncrementalUpdate()
```

## Configuration

Required defaults are created automatically:

| Setting | Default |
|---|---|
| `Season` | `2026` |
| `BaseURL` | `https://visualbaseball.com` |
| `CacheFolder` | `<workbook folder>\cache` |
| `LastSuccessfulRun` | blank |
| `RequestIntervalMs` | `1000` |
| `MaxRetries` | `3` |
| `RecheckRecentDays` | `2` |
| `Timezone` | `Asia/Seoul` |
| `MaxGamesPerRun` | `10` |
| `TestGameIds` | blank |

`MaxGamesPerRun` bounds gradual backfill. `TestGameIds` is a comma-separated temporary allowlist for acceptance testing.

## Cache and incremental behavior

Raw responses are stored as:

```text
cache/
  raw/
    2026/
      <game_id>.pending.json
      <game_id>.json
```

A pending file is promoted only after the game is officially final, Events and Pitches are written, and validation passes. A verified final game is skipped when its final raw file exists and its `Games.validation_status` is `PASS`, except for the configured recent-day recheck window.

Rows are replaced one game at a time only after that game's parse and validation succeed. Failure in another game never deletes previously valid data. The lock is `cache\update.lock` and is released in cleanup code.

Keys are:

- Games: `game_id`
- Events: `game_id + event_seq`
- Pitches: `pitch_id`, falling back to `game_id + pa_id + pitch_number`

## Limited Windows Excel acceptance test

Before scheduling a production update:

1. Set `TestGameIds` to these five confirmed final games:
   `20260328HTSK0,20260328KTLG0,20260328LTSS0,20260328OBNC0,20260328WOHH0`
2. Set `MaxGamesPerRun=5` and `RecheckRecentDays=0`.
3. Run `RunIncrementalUpdate`.
4. Confirm one `Games` row per ID, unique `Events` sequence numbers, unique pitch keys, official final-score matches, and five final raw files.
5. Run the same macro again. Confirm `events_added=0` and `pitches_added=0` in the newest `Update_Log` row.
6. Change one allowlisted game to a non-final test record only if the live schedule provides one; confirm it remains retryable and is not promoted.
7. Clear `TestGameIds`, restore `RecheckRecentDays=2`, and choose the desired production `MaxGamesPerRun`.
8. Search every workbook header and all delivered source files for excluded source-field names and confirm zero matches.

The VBA acceptance run passed for `20260328HTSK0`. The first run upserted one validated game, added 423 Events and 338 Pitches, and promoted the final raw JSON cache. The immediate second run added zero Games, Events, or Pitches and produced zero duplicate game, event, or pitch keys.

## Integration fixes

Four minimal source fixes were required by live COM compilation and smoke testing:

- `src_vba/modHttp.bas`: use `WinHttp.WinHttpRequest.5.1`; the same public token/cookies returned HTTP 403 through `MSXML2.ServerXMLHTTP.6.0` on this machine and HTTP 200 through WinHTTP.
- `src_vba/modUtils.bas`: construct the Korean final-status value with `ChrW` code points so VBA import cannot corrupt the literal.
- `src_vba/modParser.bas`: avoid the case-insensitive `jsonText`/`JsonText` name collision, encode Korean pitch-type matching through Unicode code points, and synchronize score state from the public half-inning `scoreAfter` snapshot.
- `src_vba/modValidation.bas`: validate the official final score against the final event state, including an explicit source-score adjustment event when needed.

After these changes, all imported standard-module source is ASCII-only, preventing UTF-8-to-ANSI mojibake during VBA import while preserving Korean values received at runtime.

## Daily schedule

After the real `.xlsm` exists, test the runner manually:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Run_SwingTake_Update.ps1
```

Then register the task:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install_SwingTake_Schedule.ps1
```

The task name is `VisualBaseball_SwingTake_Daily_Update`. It runs daily at 12:00 PM in the current local Windows timezone, retries up to three times, does not overlap itself, and requires the current user to be logged on with desktop Excel installed.

## Out of scope

This collector does not calculate expectancy values, pitch or Swing/Take run values, attack-zone classes, leaderboards, dashboards, or models.
# Visual Baseball 2026 collector

The original `visualbaseball_savant_2026_incremental.xlsm` remains the local VBA collector. This Python project is the separate, GitHub Actions-friendly incremental collector.

## Run

```powershell
python -m pip install -r requirements.txt
$env:PYTHONPATH = "src"
python -m visualbaseball.cli --fixture data/raw/2026/20260328HTSK0.json
pytest
```

Production runs discover the 2026 schedule, skip validated final games except recent rechecks, collect eligible PBP payloads, validate reconstructed state, and write the sole downloadable workbook at `exports/visualbaseball_savant_2026_latest.xlsx`.

Processed storage is Parquet (`games`, `events`, `pitches`) with `data/manifest.json` recording completed, incomplete, and failed games. Raw source JSON is kept under `data/raw/<season>/` only after a collection attempt. Unknown source actions are retained as `parse_status=unknown`; no spin-rate fields, run-expectancy tables, run values, or attack zones are calculated.

The scheduled workflow runs at 12:07 PM Asia/Seoul (03:07 UTC) and creates a commit only when data or the workbook changed.
