# ZA league-relative decision value · 2024–2026

`D = (S - p_swing) * (V_swing - V_take)`; ZA = `100 * sum(D) / N`, cumulative value = `sum(D)`.
No aggression/take allocation, cluster scaling, player-rank targets, or SA decorrelation.

## One integrated evaluation

The first 70% of season dates train the models; the last 30% evaluate them. RE tables and event priors use training data only. Direct action regressions and staged event models use the same pre-pitch features and training-derived RV target. The prespecified gate requires lower overall observed-action MSE and no action-specific MSE deterioration greater than 2%. Both actions improved in all three seasons, so all selected the staged model. Improvements are modest; these are observed-action prediction results, not proof of counterfactual accuracy or statistical significance.

| Season | Scored pitches | Holdout starts | Direct MSE | Event MSE | Reduction |
|---|---:|---|---:|---:|---:|
| 2024 | 222,225 | 20240808 | 0.070907 | 0.070431 | 0.67% |
| 2025 | 217,623 | 20250812 | 0.063653 | 0.063006 | 1.02% |
| 2026 | 183,044 | 20260716 | 0.067815 | 0.066748 | 1.57% |

Season reports in `data/processed/zone_decision_report_YYYY.json` include propensity/event prediction metrics, period repeatability and opposite-action support. Repeatability is descriptive: the scored periods share training observations. Sparse opposite actions remain particularly common in Waste.

## Scoring and shrinkage

Three contiguous date blocks provide out-of-fold scores for every eligible pitch. Each prediction excludes all games on its block's dates. Other blocks may be later in time; displayed season scores are retrospective cross-fits, not strictly prospective forecasts. Model choice uses the separate chronological evaluation described above, so that holdout is a development/selection set, not an untouched final test.

Features: normalized continuous location, count, base/out state, velocity, release height, park-adjusted HB/IVB, pitch type, batter stance and stadium. Training-only categorical maps treat unseen categories as missing. Batter/pitcher identity and post-pitch outcomes are not features. Legacy stance is enriched from the existing handedness lookup. Park offsets are externally supplied seasonal corrections, not re-estimated inside folds.

Conditional event probabilities cover Whiff/Foul/InPlay given Swing and Ball/CalledStrike/HBP given Take. Event RV estimates shrink from event × full state to event × count to event, with 50 prior observations. InPlay also uses a league regression on pre-pitch conditions, blended with the state prior using local InPlay support n/(n+50). RE288 states shrink toward base/out and outs priors. Inning run totals include recorded nondecision pitches before eligibility filtering.

A pitch's actual hit/home-run outcome never enters its own decision score. Other games' league outcomes provide training targets. No exit velocity or launch angle is used. The metric describes league-average execution, not the individual hitter's optimal action; observational action selection and missing counterfactuals remain limitations.

## Display and maintenance

ZA / 100 is primary, alongside cumulative value, percentile, SA and the old zone-alignment formula as a separate auxiliary judgment measure. Auxiliary judgment now uses cross-fitted called-strike probabilities from the event model; it is not an exact numerical preservation of the old model's outputs.

Five explanation regions: Heart d≤2/3; Shadow inside 2/3<d≤1; Shadow outside 1<d≤4/3; Chase 4/3<d≤2; Waste d>2, where d=max(|x|,|z|). Region/action contributions all divide by the hitter's full N and add to ZA. Location cells instead show their local per-100 rate. Overall pitch detail includes pitches outside the plotted grid. 2022–2023 remain explicitly labeled legacy seasons.

Rebuild: `OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 PYTHONPATH=src python -m visualbaseball.zone_decision --seasons 2024 2025 2026`. Daily exports invoke the new builder for these years; 2026's updated scores and player CSV are committed by the existing workflow. Inputs use the authoritative historical workbooks and current 2026 pitch table. Large reproducible pitch-level evidence is cached locally, while summaries, model reports and web JSON are committed.

Validation: 33 repository tests passed, including league-policy neutrality, take credit when its RV exceeds swing, additive contributions, exclusion of outcome features, and training-only RE construction.
