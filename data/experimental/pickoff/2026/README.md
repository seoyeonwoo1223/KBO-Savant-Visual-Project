# 2026 pickoff experiment

This directory archives exploratory 2026 pickoff/disengagement work built from Naver Sports relay text and the project's pitch data.

## Status

- Experimental archive only.
- Do not interpret `견제`-text events as a complete count of routine pickoff throws.
- The newer `투수판 이탈` crawl is a broader pitcher-disengagement signal and is substantially more complete for routine runner-control actions, but it is still not identical to literal pickoff throws.

## Files

- `team_summary.json`: original `견제`-text exploratory team counts/rates.
- `team_summary.parquet`: parquet copy of the original team summary.
- `events.parquet`: normalized original `견제`-related events.
- `audit.json`: audit used to diagnose the original source coverage.
- `disengagement_summary.json`: 2026 full-season Naver `투수판 이탈` crawl summary, team/game distribution, and base-occupancy validation.
- `disengagement_events.json`: full `투수판 이탈` event records including `currentGameState.base1/base2/base3`.
- `disengagement_events.csv`: flat event export for inspection.

## Original `견제` text experiment

- Runner pitch: a regular pitch with at least one runner on 1B, 2B, or 3B immediately before the pitch.
- Exploratory rate: Naver-recorded `견제`-related events / defensive runner-pitches × 100.
- The 2026 audit found only 174 `견제`-containing relay entries, mostly outs/errors/reviews, so this cannot represent routine pickoff-attempt frequency.

## `투수판 이탈` follow-up

The full 2026 crawl searched every available Naver `textRelayData` inning for `투수판 이탈`.

- 688 games and 6,254 innings were fetched with zero fetch-error games.
- 7,171 disengagement events were found; 7,168 were the exact routine text `투수 투수판 이탈` and 3 were explicit disengagement warnings.
- 7,153 events had at least one runner on base; 18 had the bases empty.
- Runner-present share: 99.749%.

This strongly suggests `투수판 이탈` is the useful relay signal for measuring how often a pitcher disengages while controlling runners. Keep the metric name aligned with that meaning (for example, `Disengagements / 100 runner-pitches`) unless broadcast/manual validation demonstrates that every such event is a literal pickoff throw.

## Disengagements / 100 Runner Pitches

Team-level outputs:

- `disengagement_rate_team_summary.json`
- `disengagement_rate_team_summary.csv`
- `disengagement_rate_team_summary.parquet`

Definition: runner-present `투수판 이탈` events / runner-pitches × 100.

- Numerator and denominator are restricted to the same 618 games with curated pitch data.
- 70 crawled games without a curated pitch denominator are excluded from both sides of the rate.
- Numerator excludes `투수판 이탈` records whose Naver `currentGameState` has all bases empty.
- Denominator is a curated pitch with `base_state_code_before != 0` or any runner-before id present.
- Defensive rate is attributed to the pitching team; received rate is attributed to the batting team.
- Keep the label `Disengagements`, not literal `Pickoff Throws`, because a disengagement can include a step-off without an actual throw.
