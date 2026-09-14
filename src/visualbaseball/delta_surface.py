"""Season-wise Delta = V_swing - V_take surfaces (HANDOFF Task 2).

Structure is fixed by docs/ADR-002-delta-surface.md:

  V_take(state, loc)         ABS decision function for the call, RE288 for the
                             state transition. Nothing is fitted.
  V_swing(state, count, loc) only P(result | count, loc) is smoothed; each
                             result is converted to runs by RE288 at the state.

Neither surface is fitted per base-out state, so there are no 288 surfaces.
"""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .curated import load_rows as load_curated_rows
from .swing_take import _re288, _relative_location, _state
from .zone_decision import walk_state

SEASONS = (2024, 2025, 2026)

# Home plate geometry, feet, origin at the rear tip, y increasing toward the mound.
PLATE_DEPTH_FT = 17 / 12
JUDGE_PLANE_FT = PLATE_DEPTH_FT / 2

# Recovered from 2026 take calls and held fixed for every season; see ADR-002.
# half_ft 0.890 = 43.18/2 cm plate + 2 cm KBO widening + 3.65 cm ball radius.
# The vertical pads are the ball-radius allowance on sz_top / sz_bottom.
ABS_ZONE = {"half_ft": 0.890, "pad_top_ft": 0.12, "pad_bottom_ft": 0.08}

SWING_CALLS = {"S": "whiff", "F": "foul"}
# A double play and a sacrifice are the same batted ball as an out; only the
# base-out state decides which label it gets, so folding them into "out" keeps
# the result classes state-free and leaves the state to the value table, where
# RV(out, bases, outs) already prices the double-play risk.
#
# The class comes from the last character of pa_result, not from pa_type: 2024
# carries no pa_type at all, and reading pa_type there silently classifies every
# batted ball as "other". The mapping below reproduces pa_type exactly on 2025
# and 2026, where both fields are present (each suffix maps to one pa_type).
RESULT_SUFFIX = {
    "안": "single", "이": "double", "삼": "triple", "홈": "hr", "실": "reach_on_error",
    "비": "out", "땅": "out", "선": "out", "파": "out", "병": "out", "라": "out",
    "희": "out", "F": "out", "O": "out", "": "out",
}
RESULTS = ("whiff", "foul", "out", "reach_on_error",
           "single", "double", "triple", "hr", "other")

MIN_VALUE_CELL = 25          # empirical result-value table: minimum rows per key
GRID_STEP = 0.25             # normalized units, for support diagnostics


def _f(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if np.isfinite(result) else None


def plate_crossing(row, y_ft):
    """Ball centre at a plane y_ft in front of the rear tip, from the trajectory."""
    keys = ("x0", "y0", "z0", "vx0", "vy0", "vz0", "ax", "ay", "az")
    values = {key: _f(row.get(key)) for key in keys}
    if any(value is None for value in values.values()):
        return None
    a = 0.5 * values["ay"]
    b = values["vy0"]
    c = values["y0"] - y_ft
    if a == 0:
        if b == 0:
            return None
        roots = [-c / b]
    else:
        disc = b * b - 4 * a * c
        if disc < 0:
            return None
        root = np.sqrt(disc)
        roots = [(-b - root) / (2 * a), (-b + root) / (2 * a)]
    times = [t for t in roots if t > 0]
    if not times:
        return None
    t = min(times)
    return (values["x0"] + values["vx0"] * t + 0.5 * values["ax"] * t * t,
            values["z0"] + values["vz0"] * t + 0.5 * values["az"] * t * t)


def box_distance(row, y_ft):
    """Signed distance into the ABS box at one plane, feet; positive inside."""
    top, bottom = _f(row.get("sz_top")), _f(row.get("sz_bottom"))
    if top is None or bottom is None or top <= bottom:
        return None
    crossing = plate_crossing(row, y_ft)
    if crossing is None:
        return None
    x, z = crossing
    return min(ABS_ZONE["half_ft"] - abs(x),
               (top + ABS_ZONE["pad_top_ft"]) - z,
               z - (bottom - ABS_ZONE["pad_bottom_ft"]))


def two_plane_distance(row):
    """The brief's d: the smaller signed distance across the plate's two faces.

    Positive only when the ball is inside the box at both the front and the rear
    face, so it is stricter than the call, which is decided at the middle plane
    alone. This is the geometric judgment signal, not the rule.
    """
    front = box_distance(row, PLATE_DEPTH_FT)
    rear = box_distance(row, 0.0)
    if front is None or rear is None:
        return None
    return min(front, rear)


def abs_strike(row):
    """True/False from the ABS decision function; None when geometry is missing."""
    top, bottom = _f(row.get("sz_top")), _f(row.get("sz_bottom"))
    if top is None or bottom is None or top <= bottom:
        return None
    crossing = plate_crossing(row, JUDGE_PLANE_FT)
    if crossing is None:
        return None
    x, z = crossing
    return bool(abs(x) <= ABS_ZONE["half_ft"]
                and bottom - ABS_ZONE["pad_bottom_ft"] <= z <= top + ABS_ZONE["pad_top_ft"])


def result_class(row):
    """Swing result class. None when the pitch is not a classifiable swing."""
    code = str(row.get("pitch_call_code") or "").upper()
    if code in SWING_CALLS:
        return SWING_CALLS[code]
    if code != "X":
        return None
    return RESULT_SUFFIX.get(str(row.get("pa_result") or "")[-1:], "other")


# --- state transitions -------------------------------------------------------

def _strike_transition(state):
    """(after_state, runs) for one more strike; None after-state ends the inning."""
    bases, outs, balls, strikes = state
    if strikes >= 2:
        return (bases, outs + 1, 0, 0), 0
    return (bases, outs, balls, strikes + 1), 0


def _ball_transition(state):
    bases, outs, balls, strikes = state
    if balls >= 3:
        return walk_state(state)
    return (bases, outs, balls + 1, strikes), 0


def _value(re288, state, after, runs):
    """Run value of a transition, with a completed inning worth zero."""
    if state not in re288:
        return None
    tail = 0.0 if after[1] >= 3 else re288.get(after)
    if tail is None:
        return None
    return runs + tail - re288[state]


def take_value(re288, state, is_strike):
    after, runs = _strike_transition(state) if is_strike else _ball_transition(state)
    return _value(re288, state, after, runs)


def swing_result_values(rows, re288):
    """Empirical run value of each result class by (bases, outs), RE288-based.

    Whiff and foul are analytic; batted balls are not, because advancement is not
    derivable from the call. Sparse keys fall back to (outs) then to the class.
    """
    observed = defaultdict(list)
    for row in rows:
        name = row.get("_result")
        before, after = row.get("_before"), row.get("_after")
        if name is None or before is None or after is None:
            continue
        value = _value(re288, before, after, float(row.get("runs_on_pitch") or 0))
        if value is not None:
            observed[(name, before[0], before[1])].append(value)
    by_outs = defaultdict(list)
    by_class = defaultdict(list)
    for (name, _bases, outs), values in observed.items():
        by_outs[(name, outs)].extend(values)
        by_class[name].extend(values)

    table, support = {}, {}
    for name in RESULTS:
        for bases in range(8):
            for outs in range(3):
                state = (name, bases, outs)
                pool, level = observed.get(state, []), "bases_outs"
                if len(pool) < MIN_VALUE_CELL:
                    pool, level = by_outs.get((name, outs), []), "outs"
                if len(pool) < MIN_VALUE_CELL:
                    pool, level = by_class.get(name, []), "class"
                if not pool:
                    continue
                table[state] = float(np.mean(pool))
                support[state] = (len(observed.get(state, [])), level)
    return table, support


def swing_value(table, re288, state, probabilities):
    """Sum_r P(r | count, loc) * RV(r, state); analytic for whiff and foul."""
    bases, outs, balls, strikes = state
    total, mass = 0.0, 0.0
    for name, probability in probabilities.items():
        if probability <= 0:
            continue
        if name == "whiff":
            value = take_value(re288, state, True)
        elif name == "foul":
            value = 0.0 if strikes >= 2 else take_value(re288, state, True)
        else:
            value = table.get((name, bases, outs))
        if value is None:
            continue
        total += probability * value
        mass += probability
    return total / mass if mass > 0 else None


# --- P(result | count, loc): the only fitted object ---------------------------

SPATIAL_KNOTS = 7
COUNT_KNOTS = 4
DOMAIN = 2.5          # normalized units; swings beyond this are clipped in
PENALTIES = (0.03, 0.1, 0.3, 1.0, 3.0)
CV_BLOCKS = 3


def _basis(x, z, knots):
    from sklearn.preprocessing import SplineTransformer
    grid = np.clip(np.column_stack([x, z]), -DOMAIN, DOMAIN)
    spline = SplineTransformer(n_knots=knots, degree=3, extrapolation="constant")
    marginal = spline.fit(np.array([[-DOMAIN, -DOMAIN], [DOMAIN, DOMAIN]])).transform(grid)
    width = marginal.shape[1] // 2
    left, right = marginal[:, :width], marginal[:, width:]
    return (left[:, :, None] * right[:, None, :]).reshape(len(grid), -1), spline


def _features(x, z, balls, strikes, fitted=None):
    """Common spatial surface + per-count deviation on a coarser spatial basis."""
    if fitted is None:
        fine, fine_spline = _basis(x, z, SPATIAL_KNOTS)
        coarse, coarse_spline = _basis(x, z, COUNT_KNOTS)
        fitted = (fine_spline, coarse_spline)
    else:
        fine_spline, coarse_spline = fitted
        fine = _apply(fine_spline, x, z)
        coarse = _apply(coarse_spline, x, z)
    count = (balls * 3 + strikes).astype(int)
    onehot = np.zeros((len(count), 12))
    onehot[np.arange(len(count)), count] = 1
    interaction = (onehot[:, :, None] * coarse[:, None, :]).reshape(len(count), -1)
    return np.hstack([fine, onehot[:, 1:], interaction]), fitted


def _apply(spline, x, z):
    grid = np.clip(np.column_stack([x, z]), -DOMAIN, DOMAIN)
    marginal = spline.transform(grid)
    width = marginal.shape[1] // 2
    left, right = marginal[:, :width], marginal[:, width:]
    return (left[:, :, None] * right[:, None, :]).reshape(len(grid), -1)


def fit_result_surface(rows, seed_blocks=CV_BLOCKS):
    """Penalised multinomial logit; penalty chosen by date-blocked CV log-loss."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import log_loss

    swings = [row for row in rows if row.get("_result") is not None]
    x = np.array([row["_x"] for row in swings])
    z = np.array([row["_z"] for row in swings])
    balls = np.array([row["_before"][2] for row in swings])
    strikes = np.array([row["_before"][3] for row in swings])
    y = np.array([row["_result"] for row in swings])
    features, fitted = _features(x, z, balls, strikes)

    dates = np.array([row["game_id"][:8] for row in swings])
    blocks = {date: index for index, block in enumerate(np.array_split(np.array(sorted(set(dates))), seed_blocks))
              for date in block}
    fold = np.array([blocks[date] for date in dates])

    labels = sorted(set(y))
    scores = {}
    for penalty in PENALTIES:
        losses = []
        for index in range(seed_blocks):
            train, test = fold != index, fold == index
            if len(set(y[train])) < len(labels):
                continue
            model = LogisticRegression(C=penalty, max_iter=2000)
            model.fit(features[train], y[train])
            losses.append(log_loss(y[test], model.predict_proba(features[test]), labels=list(model.classes_)))
        if losses:
            scores[penalty] = float(np.mean(losses))
    best = min(scores, key=scores.get)
    model = LogisticRegression(C=best, max_iter=3000).fit(features, y)
    return {"model": model, "spline": fitted, "penalty": best, "cv_log_loss": scores,
            "classes": list(model.classes_), "swings": len(swings)}


def fit_swing_policy(rows, seed_blocks=CV_BLOCKS):
    """League P(swing | count, loc) on the same basis; ADR-001's p in (S - p).

    Fitted here rather than reused from zone_decision so that p and Delta come
    from one generation of the surface.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import log_loss

    x = np.array([row["_x"] for row in rows])
    z = np.array([row["_z"] for row in rows])
    balls = np.array([row["_before"][2] for row in rows])
    strikes = np.array([row["_before"][3] for row in rows])
    y = np.array([int(row["_swing"]) for row in rows])
    features, fitted = _features(x, z, balls, strikes)

    dates = np.array([row["game_id"][:8] for row in rows])
    blocks = {date: index for index, block in enumerate(np.array_split(np.array(sorted(set(dates))), seed_blocks))
              for date in block}
    fold = np.array([blocks[date] for date in dates])

    scores = {}
    for penalty in PENALTIES:
        losses = []
        for index in range(seed_blocks):
            train, test = fold != index, fold == index
            model = LogisticRegression(C=penalty, max_iter=2000).fit(features[train], y[train])
            losses.append(log_loss(y[test], model.predict_proba(features[test])[:, 1], labels=[0, 1]))
        scores[penalty] = float(np.mean(losses))
    best = min(scores, key=scores.get)
    model = LogisticRegression(C=best, max_iter=3000).fit(features, y)
    probability = model.predict_proba(features)[:, 1]
    for row, value in zip(rows, probability):
        row["p_swing"] = float(value)
    return {"penalty": best, "cv_log_loss": scores,
            "observed_swing_rate": round(float(y.mean()), 6),
            "mean_p_swing": round(float(probability.mean()), 6)}


def result_probabilities(surface, x, z, balls, strikes):
    features, _ = _features(np.asarray(x), np.asarray(z), np.asarray(balls),
                            np.asarray(strikes), fitted=surface["spline"])
    return surface["model"].predict_proba(features)


# --- rows --------------------------------------------------------------------

def load_pitches(root: Path, season: int):
    rows, excluded = [], Counter()
    for row in load_curated_rows(root, "pitches", season):
        if row.get("parse_status") != "ok":
            excluded["parse_status"] += 1
            continue
        location = _relative_location(row)
        before, after = _state(row, "before"), _state(row, "after")
        if location is None or before is None or after is None or before[1] >= 3:
            excluded["state_or_location"] += 1
            continue
        call = str(row.get("pitch_call_code") or "").upper()
        if call not in {"S", "F", "X", "B", "T"}:
            excluded["unclassified_call"] += 1
            continue
        strike = abs_strike(row)
        if strike is None:
            excluded["no_trajectory_geometry"] += 1
            continue
        row["_x"], row["_z"] = location
        row["_before"], row["_after"] = before, after
        row["_swing"] = call in {"S", "F", "X"}
        row["_result"] = result_class(row) if row["_swing"] else None
        row["_abs_strike"] = strike
        row["_d"] = two_plane_distance(row)
        rows.append(row)
    return rows, dict(excluded)


def build_delta(rows, re288, table, surface):
    """Attach v_take, v_swing and delta to every row; None where undefined."""
    x = np.array([row["_x"] for row in rows])
    z = np.array([row["_z"] for row in rows])
    balls = np.array([row["_before"][2] for row in rows])
    strikes = np.array([row["_before"][3] for row in rows])
    probabilities = result_probabilities(surface, x, z, balls, strikes)
    classes = surface["classes"]
    undefined = Counter()
    for index, row in enumerate(rows):
        state = row["_before"]
        v_take = take_value(re288, state, row["_abs_strike"])
        distribution = dict(zip(classes, probabilities[index]))
        v_swing = swing_value(table, re288, state, distribution)
        row["v_take"], row["v_swing"] = v_take, v_swing
        if v_take is None or v_swing is None:
            row["delta"] = None
            undefined["v_take" if v_take is None else "v_swing"] += 1
        else:
            row["delta"] = v_swing - v_take
    return dict(undefined)


# --- Task 3: support diagnostics ---------------------------------------------

def _cell(x, z):
    return int(round(x / GRID_STEP)), int(round(z / GRID_STEP))


def support_diagnostics(rows, minimum=25, max_radius=4):
    """Local swing support at each pitch's (count, location).

    A pitch is extrapolated when no Chebyshev neighbourhood up to max_radius
    around its cell, at its own count, holds `minimum` observed swings. V_swing
    there is the model's extension of distant data, not a local average.
    """
    swings = defaultdict(int)
    takes = defaultdict(int)
    for row in rows:
        key = (row["_before"][2], row["_before"][3], *_cell(row["_x"], row["_z"]))
        (swings if row["_swing"] else takes)[key] += 1

    def local(balls, strikes, cx, cz, radius):
        return sum(count for (b, s, x, z), count in swings.items()
                   if b == balls and s == strikes and max(abs(x - cx), abs(z - cz)) <= radius)

    cache = {}
    summary = Counter()
    for row in rows:
        balls, strikes = row["_before"][2], row["_before"][3]
        cx, cz = _cell(row["_x"], row["_z"])
        key = (balls, strikes, cx, cz)
        if key not in cache:
            radius, total = 0, swings.get(key, 0)
            while total < minimum and radius < max_radius:
                radius += 1
                total = local(balls, strikes, cx, cz, radius)
            cache[key] = (total, radius, total >= minimum)
        total, radius, supported = cache[key]
        row["_support"] = total
        row["_support_radius"] = radius
        row["_extrapolated"] = not supported
        summary["extrapolated" if not supported else "supported"] += 1
    return summary, swings, takes


def support_grid(rows):
    """Per-cell counts and extrapolated share, pooled over counts, for the map."""
    grid = defaultdict(lambda: {"pitches": 0, "swings": 0, "takes": 0, "extrapolated": 0})
    for row in rows:
        entry = grid[_cell(row["_x"], row["_z"])]
        entry["pitches"] += 1
        entry["swings" if row["_swing"] else "takes"] += 1
        entry["extrapolated"] += int(row["_extrapolated"])
    return grid


# --- premise check: does base-out state move P(result | count, loc)? ----------

PREMISE_MIN = 50


def premise_check(rows, re288, table):
    """Test the structural premise that (count, loc) alone fixes the swing result
    distribution, and price the violation in runs."""
    strata = defaultdict(lambda: (Counter(), Counter()))
    for row in rows:
        if row["_result"] is None:
            continue
        key = (row["_before"][2], row["_before"][3], *_cell(row["_x"], row["_z"]))
        occupied = int(row["_before"][0] > 0)
        strata[key][occupied][row["_result"]] += 1

    usable = {key: value for key, value in strata.items()
              if sum(value[0].values()) >= PREMISE_MIN and sum(value[1].values()) >= PREMISE_MIN}
    tests = {}
    for name in RESULTS:
        numerator, variance, total = 0.0, 0.0, 0
        for empty, occupied in usable.values():
            n1, n0 = sum(occupied.values()), sum(empty.values())
            hits = occupied[name] + empty[name]
            n = n1 + n0
            if n < 2:
                continue
            numerator += occupied[name] - n1 * hits / n
            variance += n1 * n0 * hits * (n - hits) / (n * n * (n - 1))
            total += n
        if variance > 0:
            tests[name] = {"z": round(float(numerator / np.sqrt(variance)), 3), "pitches": total}

    # Runs priced: V_swing from the stratum-specific mix versus the pooled mix.
    differences = []
    for row in rows:
        if row["_result"] is None:
            continue
        key = (row["_before"][2], row["_before"][3], *_cell(row["_x"], row["_z"]))
        if key not in usable:
            continue
        empty, occupied = usable[key]
        pooled = empty + occupied
        own = occupied if row["_before"][0] > 0 else empty
        total_pooled, total_own = sum(pooled.values()), sum(own.values())
        a = swing_value(table, re288, row["_before"],
                        {k: v / total_pooled for k, v in pooled.items()})
        b = swing_value(table, re288, row["_before"],
                        {k: v / total_own for k, v in own.items()})
        if a is not None and b is not None:
            differences.append(b - a)
    differences = np.array(differences)
    null = _premise_null(rows, re288, table, usable)
    return {
        "stratified_tests": tests,
        "usable_strata": len(usable),
        "priced_swings": int(differences.size),
        "runs_per_100_swings": {
            "mean_signed": round(float(100 * differences.mean()), 4) if differences.size else None,
            "mean_absolute": round(float(100 * np.abs(differences).mean()), 4) if differences.size else None,
            "p95_absolute": round(float(100 * np.percentile(np.abs(differences), 95)), 4) if differences.size else None,
            "mean_absolute_permutation_null": null,
            "note": "mean_absolute is inflated by sampling noise in the per-stratum mix; "
                    "the excess over the permutation null is the part attributable to the state",
        },
    }


def _premise_null(rows, re288, table, usable, draws=20, seed=0):
    """Same statistic with the runner label shuffled inside each stratum."""
    generator = np.random.default_rng(seed)
    members = defaultdict(list)
    for row in rows:
        key = (row["_before"][2], row["_before"][3], *_cell(row["_x"], row["_z"]))
        if row["_result"] is not None and key in usable:
            members[key].append(row)
    values = []
    for _ in range(draws):
        total = []
        for key, group in members.items():
            occupied = np.array([row["_before"][0] > 0 for row in group])
            shuffled = generator.permutation(occupied)
            left, right = Counter(), Counter()
            for row, flag in zip(group, shuffled):
                (right if flag else left)[row["_result"]] += 1
            pooled = left + right
            pooled_total = sum(pooled.values())
            for row, flag in zip(group, shuffled):
                own = right if flag else left
                own_total = sum(own.values())
                if not own_total:
                    continue
                a = swing_value(table, re288, row["_before"], {k: v / pooled_total for k, v in pooled.items()})
                b = swing_value(table, re288, row["_before"], {k: v / own_total for k, v in own.items()})
                if a is not None and b is not None:
                    total.append(abs(b - a))
        if total:
            values.append(100 * float(np.mean(total)))
    return round(float(np.mean(values)), 4) if values else None


# --- map ---------------------------------------------------------------------

def write_support_map(grid, path: Path, cells=21):
    """Extrapolated share over the normalized zone; grey where nothing was seen."""
    from PIL import Image, ImageDraw
    size, margin = 24, 40
    span = range(-(cells // 2), cells // 2 + 1)
    width = height = size * cells + 2 * margin
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    for row_index, cz in enumerate(reversed(list(span))):
        for column, cx in enumerate(span):
            entry = grid.get((cx, cz))
            box = [margin + column * size, margin + row_index * size,
                   margin + (column + 1) * size, margin + (row_index + 1) * size]
            if not entry or entry["pitches"] == 0:
                draw.rectangle(box, fill=(235, 235, 235), outline=(255, 255, 255))
                continue
            share = entry["extrapolated"] / entry["pitches"]
            draw.rectangle(box, fill=(int(255 - 60 * (1 - share)), int(60 + 175 * (1 - share)),
                                      int(70 + 120 * (1 - share))), outline=(255, 255, 255))
    # The zone edge sits on the outer boundary of the cells centred at +/-1.
    edge = 1 / GRID_STEP + 0.5
    zone = [margin + (cells // 2 - edge) * size, margin + (cells // 2 - edge) * size,
            margin + (cells // 2 + edge + 1) * size, margin + (cells // 2 + edge + 1) * size]
    draw.rectangle(zone, outline=(0, 0, 0), width=2)
    draw.text((margin, 12), "extrapolated share (red = extrapolated, green = supported)", fill=(0, 0, 0))
    draw.text((margin, height - 26), "catcher view; box = rule-book zone; grey = no pitches", fill=(90, 90, 90))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


# --- build -------------------------------------------------------------------

def abs_call_agreement(rows):
    """How often the decision function reproduces the official take call."""
    takes = [row for row in rows if not row["_swing"]]
    called = np.array([str(row.get("pitch_call_code") or "").upper() == "T" for row in takes])
    predicted = np.array([row["_abs_strike"] for row in takes])
    if not takes:
        return {}
    return {
        "takes": len(takes),
        "agreement": round(float((predicted == called).mean()), 5),
        "rule_strike_called_ball": int(np.sum(predicted & ~called)),
        "rule_ball_called_strike": int(np.sum(~predicted & called)),
    }


def build_season(root: Path, season: int, write_map=True):
    rows, excluded = load_pitches(root, season)
    re288, re_counts = _re288(rows)
    for row in rows:
        row["raw_run_value"] = _value(re288, row["_before"], row["_after"],
                                      float(row.get("runs_on_pitch") or 0))
    table, value_support = swing_result_values(rows, re288)
    surface = fit_result_surface(rows)
    policy = fit_swing_policy(rows)
    undefined = build_delta(rows, re288, table, surface)
    summary, _, _ = support_diagnostics(rows)
    grid = support_grid(rows)
    premise = premise_check(rows, re288, table)

    deltas = np.array([row["delta"] for row in rows if row["delta"] is not None])
    extrapolated = [row for row in rows if row["_extrapolated"]]
    report = {
        "season": season,
        "pitches": len(rows),
        "excluded": excluded,
        "undefined_delta": undefined,
        "abs_decision_function": {**ABS_ZONE, "judge_plane_ft": round(JUDGE_PLANE_FT, 5),
                                  **abs_call_agreement(rows)},
        "swing_policy": policy,
        "result_surface": {"penalty": surface["penalty"], "cv_log_loss": surface["cv_log_loss"],
                           "classes": surface["classes"], "swings": surface["swings"]},
        "result_mix": dict(Counter(row["_result"] for row in rows if row["_result"] is not None)),
        "result_value_table": {
            "keys": len(table),
            "by_level": dict(Counter(level for _, level in value_support.values())),
        },
        "delta": {
            "pitches": int(deltas.size),
            "mean": round(float(deltas.mean()), 6),
            "sd": round(float(deltas.std(ddof=1)), 6),
            "quantiles": {q: round(float(np.percentile(deltas, q)), 6) for q in (1, 5, 25, 50, 75, 95, 99)},
            "swing_favoured_share": round(float((deltas > 0).mean()), 5),
        },
        "support": {
            "minimum_swings": 25,
            "extrapolated_pitches": summary["extrapolated"],
            "extrapolated_share": round(summary["extrapolated"] / len(rows), 5),
            "extrapolated_delta_mean": round(float(np.mean([r["delta"] for r in extrapolated
                                                            if r["delta"] is not None])), 6) if extrapolated else None,
            "region_shares": _region_shares(rows),
        },
        "premise_base_out_independence": premise,
        "re288": _re288_support(rows, re_counts),
    }
    destination = root / "data" / "metrics" / "delta_surface" / str(season)
    destination.mkdir(parents=True, exist_ok=True)
    _write_evidence(destination / "pitches.parquet", rows, season)
    (destination / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (destination / "support_grid.json").write_text(
        json.dumps({"grid_step": GRID_STEP,
                    "cells": [{"x": x, "z": z, **value} for (x, z), value in sorted(grid.items())]},
                   ensure_ascii=False) + "\n", encoding="utf-8")
    if write_map:
        write_support_map(grid, destination / "support_map.png")
    return report, rows


def _re288_support(rows, counts, minimum=30):
    """How thin the RE288 states are, and how many pitches sit in a thin one.

    swing_take._re288 does not shrink, so a state seen once carries an unshrunk
    mean into every V computed from it.
    """
    thin = {state: n for state, n in counts.items() if n < minimum}
    touched = 0
    for row in rows:
        before = row["_before"]
        after = row["_after"]
        if before in thin or (after[1] < 3 and after in thin):
            touched += 1
    return {
        "observed_states": len(counts),
        "min_state_pitches": min(counts.values()),
        "thin_threshold": minimum,
        "thin_states": len(thin),
        "thin_state_pitch_counts": dict(sorted(Counter(counts[s] for s in thin).items())),
        "smallest_states": [{"base_state_code": s[0], "outs": s[1], "balls": s[2], "strikes": s[3],
                             "pitches": counts[s]} for s in sorted(thin, key=lambda k: counts[k])[:10]],
        "pitches_touching_thin_state": touched,
        "share_touching_thin_state": round(touched / len(rows), 6),
    }


EVIDENCE_COLUMNS = ("pitch_id", "game_id", "game_date", "batter_id", "batter_name", "batter_team")


def _write_evidence(path, rows, season):
    """Per-pitch Delta evidence for Task 4 / 5. Reproducible, so not a source."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    payload = []
    for row in rows:
        bases, outs, balls, strikes = row["_before"]
        payload.append({
            **{name: row.get(name) for name in EVIDENCE_COLUMNS},
            "season": season,
            "swing": int(row["_swing"]),
            "p_swing": row.get("p_swing"),
            "delta": row.get("delta"),
            "v_swing": row.get("v_swing"),
            "v_take": row.get("v_take"),
            "d": row.get("_d"),
            "x_relative": row["_x"],
            "z_relative": row["_z"],
            "base_state_code": bases,
            "outs": outs,
            "balls": balls,
            "strikes": strikes,
            "abs_strike": bool(row["_abs_strike"]),
            "result": row.get("_result"),
            "extrapolated": bool(row["_extrapolated"]),
            "support": int(row["_support"]),
        })
    pq.write_table(pa.Table.from_pylist(payload), path)


def _region_shares(rows):
    from .swing_take import _region
    buckets = defaultdict(lambda: [0, 0])
    for row in rows:
        entry = buckets[_region(row["_x"], row["_z"])]
        entry[0] += 1
        entry[1] += int(row["_extrapolated"])
    return {name: {"pitches": total, "extrapolated": bad, "share": round(bad / total, 5)}
            for name, (total, bad) in sorted(buckets.items())}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--seasons", nargs="+", type=int, default=list(SEASONS))
    arguments = parser.parse_args()
    for year in arguments.seasons:
        result, _ = build_season(Path(arguments.root).resolve(), year)
        print(json.dumps(result["delta"], ensure_ascii=False), flush=True)
