"""Per-batter plate judgment metrics (HANDOFF Task 4) and the SBJ/DV overlap
diagnostic (Task 5).

Inputs are the per-pitch Delta evidence written by `delta_surface.build_season`.
Nothing here writes to web/ — publication waits until every metric is settled
(HANDOFF section 6).
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

SEASONS = (2024, 2025, 2026)
MIN_PITCHES = 300          # repo baseline for Swing/Take and ZA
PREDICTION_MIN_PITCHES = 500   # the condition the section 5 forecast table fixes
TAU_GRID = tuple(np.round(np.arange(0.05, 1.01, 0.05), 3))
BLOCKS = 3


def evidence_path(root: Path, season: int) -> Path:
    return root / "data" / "metrics" / "delta_surface" / str(season) / "pitches.parquet"


def load_evidence(root: Path, season: int):
    import pyarrow.parquet as pq
    table = pq.read_table(evidence_path(root, season))
    return {name: np.asarray(table[name].to_pylist(), dtype=object) for name in table.column_names}


# --- tau: the scale that turns signed distance into a judgment signal --------

def fit_tau(data, grid=TAU_GRID):
    """P(swing) = logistic(count fixed effect + beta * tanh(d / tau)).

    tau is picked by profile likelihood over the grid; the count enters as a
    fixed effect so the scale is not absorbed by count-specific aggression.
    """
    from sklearn.linear_model import LogisticRegression

    d = data["d"].astype(float)
    keep = np.isfinite(d)
    y = data["swing"].astype(int)[keep]
    count = (data["balls"].astype(int) * 3 + data["strikes"].astype(int))[keep]
    onehot = np.zeros((len(count), 12))
    onehot[np.arange(len(count)), count] = 1

    best = None
    profile = {}
    for tau in grid:
        z = np.tanh(d[keep] / tau).reshape(-1, 1)
        model = LogisticRegression(C=1e6, max_iter=1000).fit(np.hstack([z, onehot[:, 1:]]), y)
        probability = np.clip(model.predict_proba(np.hstack([z, onehot[:, 1:]]))[:, 1], 1e-9, 1 - 1e-9)
        loglik = float(np.sum(y * np.log(probability) + (1 - y) * np.log(1 - probability)))
        profile[float(tau)] = round(loglik, 3)
        if best is None or loglik > best[0]:
            best = (loglik, float(tau), float(model.coef_[0][0]))
    return {"tau": best[1], "beta": round(best[2], 5), "log_likelihood": round(best[0], 3),
            "profile": profile, "pitches": int(keep.sum()),
            "grid_edge": best[1] in (grid[0], grid[-1])}


def batter_beta_spread(data, tau, minimum=MIN_PITCHES):
    """Sensitivity check: how much beta varies across batters at the fitted tau."""
    from sklearn.linear_model import LogisticRegression

    d = data["d"].astype(float)
    keep = np.isfinite(d)
    z = np.tanh(d[keep] / tau)
    y = data["swing"].astype(int)[keep]
    batters = data["batter_id"].astype(str)[keep]
    values = []
    for batter in set(batters):
        index = batters == batter
        if index.sum() < minimum or len(set(y[index])) < 2:
            continue
        model = LogisticRegression(C=1e6, max_iter=1000).fit(z[index].reshape(-1, 1), y[index])
        values.append(float(model.coef_[0][0]))
    values = np.array(values)
    if values.size == 0:
        return {}
    return {"batters": int(values.size), "mean": round(float(values.mean()), 4),
            "sd": round(float(values.std(ddof=1)), 4),
            "quantiles": {q: round(float(np.percentile(values, q)), 4) for q in (10, 50, 90)}}


# --- Task 4: per-batter metrics ---------------------------------------------

def batter_metrics(data, tau, minimum=MIN_PITCHES):
    """SBJ, HS%, NS%, APR and DV per batter, with both denominators and the
    reason any of them is undefined. Undefined is never filled with zero."""
    delta = data["delta"].astype(float)
    d = data["d"].astype(float)
    swing = data["swing"].astype(int)
    p_swing = data["p_swing"].astype(float)
    extrapolated = data["extrapolated"].astype(bool)
    batters = data["batter_id"].astype(str)
    names = data["batter_name"].astype(str)
    teams = data["batter_team"].astype(str)

    usable = np.isfinite(delta) & np.isfinite(p_swing)
    index = defaultdict(list)
    for position, batter in enumerate(batters):
        if usable[position]:
            index[batter].append(position)

    rows = []
    for batter, positions in index.items():
        positions = np.array(positions)
        n = len(positions)
        swung = swing[positions]
        difference = delta[positions]
        policy = p_swing[positions]
        distance = d[positions]
        outside = extrapolated[positions]

        hittable = difference > 0
        hittable_n, non_hittable_n = int(hittable.sum()), int((~hittable).sum())
        hs = float(swung[hittable].mean()) if hittable_n else None
        ns = float(swung[~hittable].mean()) if non_hittable_n else None

        reasons = []
        if not hittable_n:
            reasons.append("no_hittable_pitches")
        if not non_hittable_n:
            reasons.append("no_non_hittable_pitches")
        if n < minimum:
            reasons.append(f"under_{minimum}_pitches")
        finite_d = np.isfinite(distance)
        if not finite_d.any():
            reasons.append("no_geometry")

        sign = 2 * swung - 1
        signal = np.tanh(distance[finite_d] / tau) if finite_d.any() else np.array([])
        sbj = float(100 * np.mean(sign[finite_d] * signal)) if signal.size else None
        supported = ~outside

        rows.append({
            "season": int(data["season"][positions[0]]),
            "batter_id": batter,
            "batter_name": names[positions[0]],
            "team": teams[positions[0]],
            "pitches": n,
            "qualified": bool(n >= minimum and hittable_n > 0 and non_hittable_n > 0),
            "sbj": _r(sbj),
            "sbj_pitches": int(finite_d.sum()),
            "hittable_swing_pct": _r(100 * hs) if hs is not None else None,
            "hittable_denominator": hittable_n,
            "non_hittable_swing_pct": _r(100 * ns) if ns is not None else None,
            "non_hittable_denominator": non_hittable_n,
            "apr": _r(100 * (hs - ns)) if hs is not None and ns is not None else None,
            "dv_avg_per_100": _r(100 * float(np.mean((swung - policy) * difference))),
            "dv_raw_per_100": _r(100 * float(np.mean((2 * swung - 1) * difference))),
            "swing_pct": _r(100 * float(swung.mean())),
            "mean_p_swing": _r(100 * float(policy.mean())),
            # Waste extrapolation is reported apart, never mixed into the headline.
            "extrapolated_pitches": int(outside.sum()),
            "extrapolated_share_pct": _r(100 * float(outside.mean())),
            "dv_avg_per_100_supported_only": _r(
                100 * float(np.mean((swung[supported] - policy[supported]) * difference[supported]))
            ) if supported.any() else None,
            "apr_supported_only": _apr(swung[supported], difference[supported]),
            "missing_reason": ";".join(reasons) or None,
        })
    return sorted(rows, key=lambda row: (-row["pitches"], row["batter_id"]))


def _r(value, digits=4):
    return None if value is None or not np.isfinite(value) else round(float(value), digits)


def _apr(swung, difference):
    hittable = difference > 0
    if not hittable.any() or hittable.all():
        return None
    return _r(100 * (float(swung[hittable].mean()) - float(swung[~hittable].mean())))


# --- Task 5: is SBJ measuring something DV does not? -------------------------

def overlap_diagnostic(data, tau, minimum=PREDICTION_MIN_PITCHES, blocks=BLOCKS, seed=0):
    """Delta = k*Z + r, then the reproducibility of per-batter mean(M*r).

    The sign-agreement rate and corr(Z, Delta) are recorded for reference only;
    HANDOFF section 3 retired them as the deciding statistic.
    """
    d = data["d"].astype(float)
    delta = data["delta"].astype(float)
    keep = np.isfinite(d) & np.isfinite(delta)
    z = np.tanh(d[keep] / tau)
    difference = delta[keep]
    swing = data["swing"].astype(int)[keep]
    batters = data["batter_id"].astype(str)[keep]
    games = data["game_id"].astype(str)[keep]

    k, intercept = np.polyfit(z, difference, 1)
    residual = difference - (k * z + intercept)
    mark = 2 * swing - 1

    reference = {
        "sign_agreement": _r(float(np.mean(np.sign(d[keep]) == np.sign(difference))), 5),
        "corr_z_delta": _r(float(np.corrcoef(z, difference)[0, 1]), 5),
        "k": _r(float(k), 6),
        "intercept": _r(float(intercept), 6),
        "residual_sd": _r(float(residual.std(ddof=1)), 6),
        "pitches": int(keep.sum()),
    }

    # Independent game blocks: a game lands whole in one block, so no batter's
    # pitches from one game are split across the halves being correlated.
    generator = np.random.default_rng(seed)
    unique = np.array(sorted(set(games)))
    assignment = {game: index for index, game in
                  zip(generator.integers(0, blocks, len(unique)), unique)}
    block = np.array([assignment[game] for game in games])

    statistic = mark * residual
    per_block = defaultdict(lambda: defaultdict(list))
    for position in range(len(statistic)):
        per_block[block[position]][batters[position]].append(statistic[position])

    per_batter = defaultdict(list)
    for values in per_block.values():
        for batter, items in values.items():
            per_batter[batter].append(len(items))

    pairs = []
    for left in range(blocks):
        for right in range(left + 1, blocks):
            shared = [b for b in per_block[left]
                      if len(per_block[left][b]) >= minimum // blocks
                      and len(per_block[right].get(b, [])) >= minimum // blocks]
            if len(shared) < 10:
                continue
            x = np.array([np.mean(per_block[left][b]) for b in shared])
            y = np.array([np.mean(per_block[right][b]) for b in shared])
            correlation = float(np.corrcoef(x, y)[0, 1]) if x.std() > 0 and y.std() > 0 else None
            pairs.append({"blocks": [left + 1, right + 1], "batters": len(shared),
                          "pearson_r": _r(correlation, 4),
                          "ci95": _fisher_interval(correlation, len(shared))})

    overall = [p["pearson_r"] for p in pairs if p["pearson_r"] is not None]
    return {
        "reference_only": reference,
        "statistic": "mean((2S-1) * r) per batter, r from Delta = k*Z + intercept",
        "minimum_pitches_per_block": minimum // blocks,
        "block_pairs": pairs,
        "median_pearson_r": _r(float(np.median(overall)), 4) if overall else None,
        "verdict": _verdict(overall),
    }


def _fisher_interval(r, n):
    if r is None or n < 4 or abs(r) >= 1:
        return None
    transformed = np.arctanh(r)
    spread = 1.96 / np.sqrt(n - 3)
    return [_r(float(np.tanh(transformed - spread)), 4), _r(float(np.tanh(transformed + spread)), 4)]


def _verdict(values):
    if not values:
        return "no_usable_block_pair"
    median = float(np.median(values))
    if median >= 0.3:
        return "reproducible: SBJ carries signal Delta does not"
    if median <= 0.1:
        return "not reproducible: treat SBJ and DV as measuring the same thing"
    return "inconclusive: reproducibility between 0.1 and 0.3"


# --- section 5 forecast table -----------------------------------------------

def split_half_reliability(data, value, minimum=PREDICTION_MIN_PITCHES, draws=200, seed=0):
    """Game-level balanced halves, raw (unshrunk, uncorrected) values.

    This fills the section 5 forecast table only. Task 6 fixes a stricter
    protocol (equal sample size across seasons, a fixed surface, the same
    procedure used for ZA's 0.810) and its number supersedes this one.
    """
    generator = np.random.default_rng(seed)
    batters = data["batter_id"].astype(str)
    games = data["game_id"].astype(str)
    eligible = {b for b, n in zip(*np.unique(batters, return_counts=True)) if n >= minimum}
    if not eligible:
        return None
    unique = np.array(sorted(set(games)))
    correlations = []
    for _ in range(draws):
        half = dict(zip(unique, generator.integers(0, 2, len(unique))))
        side = np.array([half[game] for game in games])
        left, right = [], []
        for batter in eligible:
            index = batters == batter
            a, b = index & (side == 0), index & (side == 1)
            if a.sum() < 50 or b.sum() < 50:
                continue
            first, second = value(data, a), value(data, b)
            if first is None or second is None:
                continue
            left.append(first)
            right.append(second)
        if len(left) >= 10:
            x, y = np.array(left), np.array(right)
            if x.std() > 0 and y.std() > 0:
                correlations.append(float(np.corrcoef(x, y)[0, 1]))
    if not correlations:
        return None
    return {"median_r": _r(float(np.median(correlations)), 4), "draws": len(correlations),
            "iqr": [_r(float(np.percentile(correlations, 25)), 4),
                    _r(float(np.percentile(correlations, 75)), 4)],
            "note": "raw values, uncorrected; Task 6 protocol supersedes"}


def _apr_value(data, index):
    difference = data["delta"].astype(float)[index]
    swung = data["swing"].astype(int)[index]
    finite = np.isfinite(difference)
    return _apr(swung[finite], difference[finite])


def simple_seager(root: Path, season: int):
    """The existing ST - HPT (plate_discipline.simple_seager), for section 5."""
    import pyarrow.parquet as pq
    path = root / "data" / "metrics" / "plate_discipline" / str(season) / "plate_discipline_batters.parquet"
    if not path.exists():
        return {}
    table = pq.read_table(path, columns=["batter_id", "simple_seager"])
    return {str(b): s for b, s in zip(table["batter_id"].to_pylist(),
                                      table["simple_seager"].to_pylist()) if s is not None}


def _spearman(x, y):
    if len(x) < 3:
        return None
    rank = lambda v: np.argsort(np.argsort(np.asarray(v, dtype=float)))
    a, b = rank(x), rank(y)
    if a.std() == 0 or b.std() == 0:
        return None
    return _r(float(np.corrcoef(a, b)[0, 1]), 4)


def forecast_table(root, data, tau, metrics, overlap):
    """Fill the observed column of HANDOFF section 5.

    The table's stated conditions govern: 2026, no shrinkage, raw scores,
    both classes observed, at least 500 retained pitches, and DV defined there
    as 100*mean((2S-1)*Delta) -- the raw form, not ADR-001's DV_avg.
    """
    pool = [row for row in metrics
            if row["pitches"] >= PREDICTION_MIN_PITCHES and row["apr"] is not None]
    seager = simple_seager(root, data["season"][0] if len(data["season"]) else 0)
    paired = [row for row in pool if row["batter_id"] in seager]

    reliability_apr = split_half_reliability(data, _apr_value)
    reliability_seager = _seager_split_half(root, data)

    return {
        "conditions": {"season": int(data["season"][0]), "shrinkage": "none",
                       "minimum_pitches": PREDICTION_MIN_PITCHES, "batters": len(pool),
                       "dv_definition": "100 * mean((2S-1) * Delta), as section 5 fixes it"},
        "rows": [
            {"quantity": "mean(sign(d) == sign(Delta))", "point": 0.84, "interval": [0.75, 0.92],
             "observed": overlap["reference_only"]["sign_agreement"]},
            {"quantity": "corr(tanh(d/tau), Delta) per pitch", "point": 0.65, "interval": [0.45, 0.80],
             "observed": overlap["reference_only"]["corr_z_delta"]},
            {"quantity": "rho(raw ST-HPT, DV/100) per batter", "point": 0.35, "interval": [0.10, 0.60],
             "observed": _spearman([seager[r["batter_id"]] for r in paired],
                                   [r["dv_raw_per_100"] for r in paired]),
             "batters": len(paired)},
            {"quantity": "rho(HS%-NS%, DV/100) per batter", "point": 0.72, "interval": [0.55, 0.85],
             "observed": _spearman([r["apr"] for r in pool], [r["dv_raw_per_100"] for r in pool]),
             "batters": len(pool)},
            {"quantity": "new APR split-half (raw)", "point": 0.60, "interval": [0.45, 0.72],
             "observed": reliability_apr["median_r"] if reliability_apr else None,
             "detail": reliability_apr},
            {"quantity": "raw ST-HPT split-half (raw)", "point": 0.40, "interval": [0.20, 0.55],
             "observed": reliability_seager["median_r"] if reliability_seager else None,
             "detail": reliability_seager},
        ],
    }


def _seager_split_half(root, data, draws=200, seed=0):
    """ST - HPT rebuilt from the same pitches, so both halves use one split."""
    difference = data["delta"].astype(float)
    abs_strike = data["abs_strike"].astype(bool)
    swing = data["swing"].astype(int)
    batters = data["batter_id"].astype(str)
    games = data["game_id"].astype(str)
    del difference

    def value(index):
        zone_swing = int((abs_strike[index] & (swing[index] == 1)).sum())
        out_swing = int((~abs_strike[index] & (swing[index] == 1)).sum())
        zone_take = int((abs_strike[index] & (swing[index] == 0)).sum())
        out_take = int((~abs_strike[index] & (swing[index] == 0)).sum())
        if not (out_take + zone_swing) or not (zone_take + out_take):
            return None
        # plate_discipline.simple_seager: 100 * [D/(A+D) - C/(C+D)]
        return 100 * (out_take / (zone_swing + out_take) - zone_take / (zone_take + out_take))

    generator = np.random.default_rng(seed)
    eligible = {b for b, n in zip(*np.unique(batters, return_counts=True)) if n >= PREDICTION_MIN_PITCHES}
    unique = np.array(sorted(set(games)))
    correlations = []
    for _ in range(draws):
        half = dict(zip(unique, generator.integers(0, 2, len(unique))))
        side = np.array([half[game] for game in games])
        left, right = [], []
        for batter in eligible:
            index = batters == batter
            a, b = index & (side == 0), index & (side == 1)
            if a.sum() < 50 or b.sum() < 50:
                continue
            first, second = value(a), value(b)
            if first is None or second is None:
                continue
            left.append(first)
            right.append(second)
        if len(left) >= 10:
            x, y = np.array(left), np.array(right)
            if x.std() > 0 and y.std() > 0:
                correlations.append(float(np.corrcoef(x, y)[0, 1]))
    if not correlations:
        return None
    return {"median_r": _r(float(np.median(correlations)), 4), "draws": len(correlations),
            "iqr": [_r(float(np.percentile(correlations, 25)), 4),
                    _r(float(np.percentile(correlations, 75)), 4)],
            "note": "raw values, uncorrected; Task 6 protocol supersedes"}


# --- build -------------------------------------------------------------------

def build_season(root: Path, season: int):
    from .export_excel import export_plate_judgment

    data = load_evidence(root, season)
    tau = fit_tau(data)
    spread = batter_beta_spread(data, tau["tau"])
    metrics = batter_metrics(data, tau["tau"])
    overlap = overlap_diagnostic(data, tau["tau"])
    qualified = [row for row in metrics if row["qualified"]]

    report = {
        "season": season,
        "pitches": int(len(data["delta"])),
        "batters": len(metrics),
        "qualified_batters": len(qualified),
        "minimum_pitches": MIN_PITCHES,
        "tau": tau,
        "batter_beta_spread": spread,
        "missing_reasons": _reason_counts(metrics),
        "extrapolation": {
            "note": "Waste extrapolation is reported apart; see the *_supported_only columns",
            "mean_share_pct": _r(float(np.mean([r["extrapolated_share_pct"] for r in metrics])), 4),
            "max_share_pct": _r(max(r["extrapolated_share_pct"] for r in metrics), 4),
            "dv_avg_shift_from_dropping": _r(float(np.mean(
                [r["dv_avg_per_100_supported_only"] - r["dv_avg_per_100"] for r in qualified
                 if r["dv_avg_per_100_supported_only"] is not None])), 4),
        },
        "overlap_task5": overlap,
        "limitations": [
            "The ABS decision function leaves an asymmetric residual: pitches the rule "
            "calls a strike are called balls three to five times more often than the "
            "reverse. Unresolved; see ADR-002.",
            "swing_take._re288 does not shrink, so states seen a handful of times carry "
            "an unshrunk run expectancy. See the delta_surface report's re288 block.",
            "Delta in the Waste region is partly extrapolated and strongly take-favoured; "
            "the *_supported_only columns exclude it.",
        ],
    }
    if season == 2026:
        report["forecast_table_section5"] = forecast_table(root, data, tau["tau"], metrics, overlap)

    destination = root / "data" / "metrics" / "plate_judgment" / str(season)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (destination / "batters.json").write_text(
        json.dumps({"season": season, "minimum_pitches": MIN_PITCHES, "batters": metrics},
                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    export_plate_judgment(root, season, {"Batters": metrics, "Report": _flatten(report)})
    return report


def _reason_counts(metrics):
    counter = defaultdict(int)
    for row in metrics:
        for reason in (row["missing_reason"] or "").split(";"):
            if reason:
                counter[reason] += 1
    return dict(sorted(counter.items()))


def _flatten(report, prefix=""):
    rows = []
    for key, value in report.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            rows.extend(_flatten(value, f"{name}."))
        elif isinstance(value, list):
            rows.append({"key": name, "value": json.dumps(value, ensure_ascii=False)})
        else:
            rows.append({"key": name, "value": value})
    return rows


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--seasons", nargs="+", type=int, default=list(SEASONS))
    arguments = parser.parse_args()
    for year in arguments.seasons:
        result = build_season(Path(arguments.root).resolve(), year)
        print(year, "batters", result["qualified_batters"], "tau", result["tau"]["tau"],
              "overlap", result["overlap_task5"]["median_pearson_r"], flush=True)
