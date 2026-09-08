# ZA v5 · league-relative decision value · 2024–2026

`D = (S - p_swing) * (V_swing - V_take)`. ZA = `100 * sum(D) / N`; cumulative value = `sum(D)`. No player-rank targets, action-allocation targets or SA decorrelation.

## Inputs and scoring states

Historical workbooks provide both Pitches and Events. Current 2026 uses processed pitch and event tables, including an alternate CLI storage root. Source hashes invalidate historical caches. A clean build creates its cache directory.

Known, timed non-pitch runs enter inning remaining-run targets. Halves with unresolved score repairs or inconsistent score timelines are excluded before eligibility filtering; no run receives an invented timestamp. Incomplete halves do not train RE. Reports give exclusions and reasons. This trades coverage for reliability; it does not repair the underlying source data.

RE288 shrinks state means toward base/out and outs priors from reliable, complete training innings. Weighted constrained least squares projects one shared table: an ordinary ball/walk/HBP cannot reduce RE plus runs, and a strike/strikeout cannot increase it. Values are nonnegative and terminal outs are zero. Ordinary event RV is the exact rule transition minus pre-pitch RE; a two-strike foul is exactly zero. InPlay retains training-only state/count shrinkage and a pre-pitch regression blended by local InPlay support `n/(n+50)`.

These transitions describe ordinary outcomes. Dropped third strikes, bunt fouls, runner movement on non-contact pitches and unrecorded intent cannot be fully distinguished with the six-event taxonomy. They are not claims of individual optimal execution.

## Predictions and sparse support

Features: normalized location, count, base/out state, velocity, release height, park-adjusted HB/IVB, pitch type, stance and stadium. Identity and post-pitch outcomes are not features. Unknown categories are missing; all-missing training columns are ignored through a constant. Supplied park offsets are external seasonal corrections, not estimated within folds.

Conditional models estimate Whiff/Foul/InPlay given Swing and Ball/CalledStrike/HBP given Take. Sparse Swing probabilities blend toward training-only count/region/type/stance frequencies, themselves shrunk toward count/region and action priors, with 50 prior observations. The model weight is `n/(n+50)` for same-action neighborhood counts. Neighborhoods use normalized half-unit location cells, count, pitch type, stance, 10 km/h velocity and 10 cm movement bins. Take probabilities retain the location-sensitive fitted model. Opposite-action support uses the same detailed bins, with the legacy coarse count retained in pitch evidence. These counts diagnose coverage; they do not establish causal overlap or effective sample size.

Propensity calibration is optional within each training set. Game-group out-of-fold probabilities feed an isotonic calibrator; a training-date 80/20 split must improve log loss and not worsen Brier score before fitting it on all training OOF pairs. No scored-game outcome enters this gate. Whether calibration applied is recorded per fit.

## Evaluation and uncertainty

The first 60% of dates train a development evaluation on the next 20%; the final 20% evaluate the frozen algorithm trained on the first 80%. Direct and unpooled value models are diagnostic baselines. The final set does not select settings. The event model is retained for coherent transitions, not because an observed-action MSE winner necessarily identifies counterfactual value. Reports include observed-action MSE, event loss, raw/calibrated propensity metrics and calibration bins.

Three contiguous date-block cross-fits produce season scores. Every scored game is excluded from its model, RE, priors and calibration. Other blocks can be later dates: season estimates are retrospective, not prospective forecasts. Period correlations are descriptive because training observations overlap.

Qualified hitters have at least 300 retained pitches. Their 95% intervals use 1,000 game-cluster bootstrap resamples with fixed predictions, not a full model refit. They omit model uncertainty and unidentified counterfactual bias. Ranks are point-estimate ordering, not established superiority.

Five regions partition normalized distance `d=max(abs(x),abs(z))`: Heart ≤2/3, Shadow inside ≤1, Shadow outside ≤4/3, Chase ≤2, Waste >2. Region/action contributions divide by the hitter's full N and add to ZA. Map cells show local per-100 rates. The player view shows the interval and low opposite-support percentage; season notes show excluded coverage. 2022–2023 remain legacy seasons.

## Reproduction

Use Python 3.12.10 and `python -m pip install -r requirements.txt -c constraints-za.txt`. Set `PYTHONPATH=src`, `OMP_NUM_THREADS=2` and `OPENBLAS_NUM_THREADS=2`, then run `python -m visualbaseball.zone_decision --seasons 2024 2025 2026`. Run `python -m pytest` with the same environment.

Daily exports call this builder. `data/processed/zone_decision_report_YYYY.json` records input/source SHA-256, package versions, fresh metrics, exclusions and constraint diagnostics. Player CSVs and web JSON derive from the same pitch calculations; `.cache/zone_decision_pitches_YYYY.parquet` retains local pitch evidence. Constraints reduce drift; cross-platform bitwise identity is not promised.

Tests exercise policy neutrality, additive contributions, score-repair exclusion and known non-pitch runs, all 288 states' legal transitions, and actual fitted predictions under mutation of held-out outcomes. Observed-action prediction does not validate the unobserved opposite action, omitted execution skill or bunt intent.
