# 2026 pickoff experiment

This directory archives a one-off exploratory pickoff dataset built from Naver Sports relay text and the project's 2026 curated pitch data.

## Status

- Experimental archive only.
- Do not publish this as a production metric or use it as a true count of routine pickoff throws.
- Naver relay text materially under-records routine pickoff attempts that do not produce an out, error, review, or other notable runner event.

## Files

- `team_summary.json`: team-level exploratory counts and rates per 100 runner-pitches.
- `team_summary.parquet`: parquet copy of the team summary.
- `events.parquet`: normalized Naver-recorded pickoff-related events.
- `audit.json`: audit used to diagnose source coverage.

## Metric definition used in the experiment

- Runner pitch: a regular pitch with at least one runner on 1B, 2B, or 3B immediately before the pitch.
- Exploratory rate: Naver-recorded pickoff-related events / defensive runner-pitches × 100.
- Received rate: the same events attributed to the offensive team / offensive runner-pitches × 100.

## Known limitation

The 2026 backfill found 174 Naver relay entries containing `견제`; the audit showed that most were associated with outs or throwing errors, with very few routine no-out/no-error attempts. The source therefore cannot support a true team pickoff-attempt frequency leaderboard.
