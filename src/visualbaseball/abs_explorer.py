"""Experimental ABS Zone Explorer build (manual, outside the daily pipeline).

    PYTHONPATH=src python -m visualbaseball.abs_explorer            # research + web data
    PYTHONPATH=src python -m visualbaseball.abs_explorer --skip-trackman

Reads curated pitches/events (2022-2026), data/curated/players/player_bio.parquet and, for the
tracking audit, the TrackMan history through analysis/movement_calibration/match_trackman.py.
Writes research outputs to data/experimental/abs/ and the viewer data to web/data/abs/.
Nothing here changes curated data or any production metric. Methods: analysis/abs/README.md.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.optimize import minimize
from scipy.stats import norm

from . import abs_zone as az
from . import abs_run_value as arv
from .batter_stance import load_batter_hands, resolved_batter_stance
from .curated import load_rows, load_table
from .publish import write_json
from .swing_take import _state
from .zone_decision import RunExpectancy, reliable_halves

ROOT = Path(__file__).resolve().parents[2]
UMPIRE_SEASONS = (2022, 2023)
ABS_SEASONS = az.ABS_SEASONS
SEASONS = UMPIRE_SEASONS + ABS_SEASONS
OUT = Path("data/experimental/abs")
WEB_OUT = Path("web/data/abs")
STATUS = "experimental"
PITCH_COLUMNS = [
    "pitch_id", "game_id", "game_date", "stadium", "inning", "inning_half", "batter_id", "batter_name", "pitcher_id",
    "pitcher_name", "batter_stance", "pitch_call_code", "is_pa_terminal", "pa_type", "pa_result", "parse_status",
    "pitch_type_code", "pitch_type_kr", "velocity_kmh", "horizontal_movement_cm", "vertical_movement_cm",
    "px", "pz", "sz_top", "sz_bottom", "x0", "y0", "z0", "vx0", "vy0", "vz0", "ax", "ay", "az",
    "plate_x_error_cm", "plate_z_error_cm", "release_x_50", "balls_before", "strikes_before", "outs_before", "base_state_code_before",
]
RE_COLUMNS = ["game_id", "inning", "inning_half", "event_seq", "runs_on_pitch", "away_score_before", "away_score_after",
              "home_score_before", "home_score_after", "outs_before", "outs_after", "base_state_code_before",
              "balls_before", "strikes_before"]
TRAJECTORY = ["x0", "y0", "z0", "vx0", "vy0", "vz0", "ax", "ay", "az"]
# za7: an ABS-season row whose reported point is more than 1 cm off its own trajectory mixes two records.
LOCATION_TOLERANCE_CM = 1.0
BOUNDARY_BAND_CM = 10.0
RADIUS_GRID = tuple(round(3.50 + .02 * i, 2) for i in range(16))
ASSUMED_ERROR_CM = (0.5, 1.0, 2.0)
QUALIFIED_TAKES = {"batter": 400, "pitcher": 400}
DETAIL_MIN_TAKES = 150
BOOTSTRAP_REPS = 1000
GRID_X_CM = (-60.0, 60.0, 6.0)
GRID_Z_SHARE = (0.10, 0.76, 0.03)
COUNT_FILTERS = ("all", "s0", "s1", "s2")
STANCE_FILTERS = ("all", "L", "R")
GROUP_FILTERS = ("all", "fastball", "breaking", "offspeed")
REGION_BANDS = ((-np.inf, -5.0, "out"), (-5.0, 0.0, "edge_out"), (0.0, 5.0, "edge_in"), (5.0, np.inf, "heart"))


def r4(value):
    return None if value is None or not np.isfinite(value) else round(float(value), 4)


# ---------------------------------------------------------------- load

def load_pitches(root: Path, season: int, batter_hands: dict) -> pd.DataFrame:
    df = load_table(root, "pitches", season, columns=PITCH_COLUMNS).to_pandas()
    df["season"] = season
    # Curated batter_stance is empty before 2025; resolve it from player_bio as every pitch metric does.
    df["batter_stance"] = [resolved_batter_stance(r, batter_hands)
                           for r in df[["batter_stance", "batter_id", "release_x_50"]].to_dict("records")]
    for column in TRAJECTORY + ["px", "pz", "sz_top", "sz_bottom", "velocity_kmh", "horizontal_movement_cm",
                                "vertical_movement_cm", "plate_x_error_cm", "plate_z_error_cm"]:
        df[column] = pd.to_numeric(df[column], errors="coerce").astype(float)
    df["batter_id"] = df["batter_id"].astype(str)
    df["pitcher_id"] = df["pitcher_id"].astype(str)
    df["pitch_group"] = [arv.pitch_group(r) for r in df[["pitch_id", "pitch_type_code", "pitch_type_kr"]].to_dict("records")]
    from .pitch_types import pitch_code
    df["pitch_code"] = [pitch_code(r) for r in df[["pitch_id", "pitch_type_code", "pitch_type_kr"]].to_dict("records")]
    return df


def is_take(df: pd.DataFrame) -> pd.Series:
    """Recorded Ball or Called Strike, never a hit-by-pitch (no ball/strike call)."""
    hbp = df["is_pa_terminal"].fillna(False).astype(bool) & (
        df["pa_type"].fillna("").str.lower().eq("hbp") | df["pa_result"].fillna("").eq("사구"))
    return df["pitch_call_code"].isin(arv.TAKE_CALLS) & ~hbp & df["parse_status"].eq("ok")


def add_planes(df: pd.DataFrame) -> None:
    args = [df[c].to_numpy() for c in TRAJECTORY]
    df["x_mid_cm"], df["z_mid_cm"] = az.plane_position_cm(*args, az.MID_PLANE_Y_FT)
    _, df["z_back_cm"] = az.plane_position_cm(*args, az.BACK_PLANE_Y_FT)
    df["x_front_cm"], df["z_front_cm"] = az.plane_position_cm(*args, az.FRONT_PLANE_Y_FT)


def height_table(frames: dict[int, pd.DataFrame]) -> tuple[pd.Series, dict]:
    """Batter height implied by VB's ABS zone: per-season mode, then the median over ABS seasons."""
    per_season, stability = {}, {}
    for season in ABS_SEASONS:
        df = frames[season]
        height = pd.Series(az.implied_height_cm(df["sz_top"].to_numpy(), df["sz_bottom"].to_numpy(), season), index=df.index)
        df["pitch_height_cm"] = height
        valid = df.assign(h=height.round(1)).dropna(subset=["h"])
        per_season[season] = valid.groupby("batter_id")["h"].agg(lambda v: v.mode().iloc[0])
        changes = valid.groupby("batter_id")["h"].nunique()
        stability[str(season)] = {
            "pitches": int(len(df)), "inconsistent_or_missing_zone": int(height.isna().sum()),
            "batters": int(len(changes)), "batters_single_height": int((changes == 1).sum()),
            "sz_ratio_median": r4(float(np.nanmedian(df["sz_top"] / df["sz_bottom"]))),
            "rule_ratio": r4(az.rule_for(season).top_ratio / az.rule_for(season).bottom_ratio),
        }
    table = pd.concat(per_season, axis=1)
    for a, b in ((2024, 2025), (2025, 2026)):
        both = table.dropna(subset=[a, b])
        diff = (both[b] - both[a]).abs()
        stability[f"{a}_to_{b}"] = {"batters": int(len(both)), "abs_diff_cm_median": r4(diff.median()),
                                    "abs_diff_cm_p90": r4(diff.quantile(.9)), "abs_diff_cm_max": r4(diff.max())}
    return table.median(axis=1), stability


# ---------------------------------------------------------------- Phase 1: reconstruction

def recorded_zone_cm(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """VB's per-pitch ABS zone (sz_top/sz_bottom = rule share x registered height, 0.001 ft precision)."""
    top, bottom = df["sz_top"].to_numpy() * az.CM_PER_FOOT, df["sz_bottom"].to_numpy() * az.CM_PER_FOOT
    valid = top > bottom
    return np.where(valid, top, np.nan), np.where(valid, bottom, np.nan)


def reconstruct(df: pd.DataFrame, season: int, radius: float = az.BALL_RADIUS_CM) -> None:
    top, bottom = recorded_zone_cm(df)
    margins = az.zone_margins_cm(df["x_mid_cm"], df["z_mid_cm"], df["z_back_cm"], top, bottom, season, radius)
    df["zone_margin_cm"], edge = az.zone_margin_cm(margins)
    df["binding_edge"] = az.edge_group(edge)
    df["abs_strike"] = az.abs_strike(df["zone_margin_cm"])
    off_x = (df["px"] * az.CM_PER_FOOT - df["x_mid_cm"]).abs()
    off_z = (df["pz"] * az.CM_PER_FOOT - df["z_front_cm"]).abs()
    df["location_mixed"] = (off_x > LOCATION_TOLERANCE_CM) | (off_z > LOCATION_TOLERANCE_CM)
    df["recon_status"] = np.select(
        [df["x_mid_cm"].isna() | df["z_back_cm"].isna(), np.isnan(top), df["location_mixed"]],
        ["no_trajectory", "no_zone", "location_off_trajectory"], "ok")


def probit_fit(margin, strike) -> dict:
    """P(recorded strike) = Phi((margin - bias) / sigma): bias shifts our boundary, sigma is the disagreement width."""
    margin, strike = np.asarray(margin, float), np.asarray(strike, float)
    if margin.size < 50 or strike.min() == strike.max():
        return {"n": int(margin.size), "bias_cm": None, "sigma_cm": None}

    def nll(theta):
        p = np.clip(norm.cdf((margin - theta[0]) / np.exp(theta[1])), 1e-9, 1 - 1e-9)
        return -np.sum(strike * np.log(p) + (1 - strike) * np.log(1 - p))
    fit = minimize(nll, x0=[0.0, np.log(0.5)], method="Nelder-Mead", options={"xatol": 1e-4, "fatol": 1e-6, "maxiter": 2000})
    return {"n": int(margin.size), "bias_cm": r4(fit.x[0]), "sigma_cm": r4(float(np.exp(fit.x[1])))}


def agreement_rows(df: pd.DataFrame, key: str | None) -> list[dict]:
    groups = [("all", df)] if key is None else sorted(df.groupby(key), key=lambda item: -len(item[1]))
    rows = []
    for name, part in groups:
        agree = part["abs_strike"] == part["recorded_strike"]
        band = part[part["zone_margin_cm"].abs() <= BOUNDARY_BAND_CM]
        far = part[(~agree) & (part["zone_margin_cm"].abs() > 2.0)]
        rows.append({"group": str(name), "takes": int(len(part)), "agreement": r4(agree.mean()),
                     "mismatches": int((~agree).sum()), "mismatches_beyond_2cm": int(len(far)),
                     "boundary_takes": int(len(band)),
                     "boundary_agreement": r4((band["abs_strike"] == band["recorded_strike"]).mean()) if len(band) else None,
                     **probit_fit(band["zone_margin_cm"], band["recorded_strike"])})
    return rows


def reconstruction_report(frames: dict[int, pd.DataFrame]) -> tuple[dict, pd.DataFrame]:
    report, mismatches = {"radius_cm": az.BALL_RADIUS_CM, "seasons": {}}, []
    pooled = []
    for season in ABS_SEASONS:
        df = frames[season]
        takes = df[df["take"]]
        status = takes["recon_status"].value_counts().to_dict()
        ok = takes[takes["recon_status"] == "ok"].copy()
        pooled.append(ok)
        month = ok["game_date"].astype(str).str[5:7]
        # The 2024 zone applied to this season's pitches, to size the rule change.
        rule_shift = None
        if season >= 2025:
            # Registered height from the season's own rule; NaN heights (zone off the rule ratio) drop out.
            top24, bottom24 = (ok["pitch_height_cm"] * ratio for ratio in (az.ABS_RULES[2024].top_ratio, az.ABS_RULES[2024].bottom_ratio))
            margins24 = az.zone_margins_cm(ok["x_mid_cm"], ok["z_mid_cm"], ok["z_back_cm"], top24, bottom24, 2024)
            strike24 = az.abs_strike(az.zone_margin_cm(margins24)[0])
            known = np.isfinite(strike24)
            changed = known & (strike24 != ok["abs_strike"])
            rule_shift = {"takes_compared": int(known.sum()), "takes_called_differently_under_2024_rule": int(changed.sum()),
                          "share": r4(changed.sum() / known.sum()),
                          "strike_to_ball": int(((strike24 == 1) & (ok["abs_strike"] == 0)).sum()),
                          "ball_to_strike": int(((strike24 == 0) & (ok["abs_strike"] == 1)).sum())}
        report["seasons"][str(season)] = {
            "takes": int(len(takes)), "status": {k: int(v) for k, v in status.items()},
            "overall": agreement_rows(ok, None)[0],
            "by_edge": agreement_rows(ok, "binding_edge"),
            "by_pitch_group": agreement_rows(ok, "pitch_group"),
            "by_pitch_code": agreement_rows(ok[ok["pitch_code"] != ""], "pitch_code"),
            "by_stadium": agreement_rows(ok, "stadium"),
            "by_month": agreement_rows(ok.assign(month=month), "month"),
            "rule_change_vs_2024": rule_shift,
        }
        bad = ok[ok["abs_strike"] != ok["recorded_strike"]]
        mismatches.append(bad[["pitch_id", "season", "game_date", "stadium", "pitcher_name", "batter_name", "pitch_code",
                               "pitch_call_code", "zone_margin_cm", "binding_edge", "x_mid_cm", "z_mid_cm", "z_back_cm",
                               "pitch_height_cm", "velocity_kmh"]])
    pooled = pd.concat(pooled)
    report["pooled_2024_2026"] = {"overall": agreement_rows(pooled, None)[0], "by_edge": agreement_rows(pooled, "binding_edge"),
                                  "by_pitch_code": agreement_rows(pooled[pooled["pitch_code"] != ""], "pitch_code"),
                                  "by_stadium": agreement_rows(pooled, "stadium")}
    report["radius_scan"] = radius_scan(pooled)
    table = pd.concat(mismatches).sort_values(["season", "game_date", "pitch_id"])
    table["far_from_boundary"] = table["zone_margin_cm"].abs() > 2.0
    return report, table


def radius_scan(ok: pd.DataFrame) -> list[dict]:
    rows = []
    for radius in RADIUS_GRID:
        for mode in ("bottom_only", "none"):
            hits = 0
            for season, part in ok.groupby("season"):
                top, bottom = recorded_zone_cm(part)
                margins = az.zone_margins_cm(part["x_mid_cm"], part["z_mid_cm"], part["z_back_cm"], top, bottom, season, radius)
                if mode == "none":
                    margins["bottom_back"] = margins["bottom_back"] - az.rule_for(season).back_bottom_offset_cm
                hits += int((az.abs_strike(az.zone_margin_cm(margins)[0]) == part["recorded_strike"]).sum())
            rows.append({"radius_cm": radius, "back_plane_offset": mode, "agreement": r4(hits / len(ok)), "mismatches": int(len(ok) - hits)})
    return rows


# ---------------------------------------------------------------- Phase 3: umpire model

def pitcher_hands(root: Path) -> dict:
    source = root / "data/curated/players/player_bio.parquet"
    if not source.exists():
        return {}
    return {str(r["player_id"]): r.get("throws") for r in pq.read_table(source, columns=["player_id", "throws"]).to_pylist()}


def umpire_features(df: pd.DataFrame, heights: pd.Series, hands: dict, season_value: int | None = None) -> pd.DataFrame:
    """Front-plane location (the plane VB reported before 2024), batter height and context.

    Before 2024 VB px is the front-plane x, so a pitch without a trajectory keeps its reported px.
    From 2024 px is the middle plane, so the front-plane x needs the trajectory; such rows stay NaN.
    """
    out = pd.DataFrame(index=df.index)
    x_front = df["x_front_cm"].to_numpy()
    if int(df["season"].iloc[0]) < 2024:
        x_front = np.where(np.isfinite(x_front), x_front, df["px"].to_numpy() * az.CM_PER_FOOT)
    out["x_front_cm"] = x_front
    out["z_front_cm"] = np.where(np.isfinite(df["z_front_cm"]), df["z_front_cm"], df["pz"] * az.CM_PER_FOOT)
    out["height_cm"] = df["batter_id"].map(heights).astype(float)
    out["z_front_share"] = out["z_front_cm"] / out["height_cm"]
    out["stance"] = df["batter_stance"].map({"L": 0, "R": 1}).astype(float)
    out["pitcher_throws"] = df["pitcher_id"].map(hands).map({"L": 0, "R": 1}).astype(float)
    out["balls_before"] = pd.to_numeric(df["balls_before"], errors="coerce").astype(float)
    out["strikes_before"] = pd.to_numeric(df["strikes_before"], errors="coerce").astype(float)
    out["pitch_group"] = df["pitch_group"].map({g: i for i, g in enumerate(arv.GROUP_ORDER)}).astype(float)
    for column in ("velocity_kmh", "horizontal_movement_cm", "vertical_movement_cm"):
        out[column] = df[column]
    out["season"] = float(season_value if season_value is not None else df["season"].iloc[0])
    return out[list(arv.UMPIRE_FEATURES)]


def complete_features(features: pd.DataFrame) -> pd.Series:
    required = ["x_front_cm", "z_front_cm", "height_cm", "balls_before", "strikes_before"]
    return features[required].notna().all(axis=1)


def evaluate(p, y) -> dict:
    from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
    p, y = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6), np.asarray(y, int)
    return {"n": int(y.size), "log_loss": r4(log_loss(y, p)), "brier": r4(brier_score_loss(y, p)), "auc": r4(roc_auc_score(y, p)),
            "mean_pred": r4(p.mean()), "observed": r4(y.mean()), "calibration": arv.calibration_bins(p, y)}


def fit_umpire(train: pd.DataFrame) -> tuple[object, dict, np.ndarray]:
    """Final model on all of 2022-2023, its validation report and game-grouped out-of-fold predictions."""
    from sklearn.model_selection import GroupKFold
    X, y, games = train[list(arv.UMPIRE_FEATURES)], train["y"].to_numpy(), train["game_id"].to_numpy()
    oof = np.full(len(train), np.nan)
    for fit_idx, test_idx in GroupKFold(5).split(X, y, games):
        model = arv.umpire_model().fit(X.iloc[fit_idx], y[fit_idx])
        oof[test_idx] = model.predict_proba(X.iloc[test_idx])[:, 1]
    seasons = train["season_id"].to_numpy()
    report = {"game_grouped_5fold": {str(s): evaluate(oof[seasons == s], y[seasons == s]) for s in UMPIRE_SEASONS}}
    boundary = train["boundary"].to_numpy()
    report["game_grouped_5fold_boundary"] = {str(s): evaluate(oof[(seasons == s) & boundary], y[(seasons == s) & boundary]) for s in UMPIRE_SEASONS}
    first, second = seasons == UMPIRE_SEASONS[0], seasons == UMPIRE_SEASONS[1]
    temporal = arv.umpire_model().fit(X[first].assign(season=float(UMPIRE_SEASONS[0])), y[first])
    report["temporal_2022_to_2023"] = evaluate(temporal.predict_proba(X[second].assign(season=float(UMPIRE_SEASONS[0])))[:, 1], y[second])
    from sklearn.linear_model import LogisticRegression
    base = ["x_front_cm", "z_front_share"]
    design = lambda f: np.column_stack([f[base].to_numpy(), f[base].to_numpy() ** 2, np.abs(f["x_front_cm"].to_numpy())])
    baseline = LogisticRegression(max_iter=2000).fit(design(X[first]), y[first])
    report["baseline_location_logistic_2022_to_2023"] = evaluate(baseline.predict_proba(design(X[second]))[:, 1], y[second])
    report["baseline_location_logistic_2022_to_2023"].pop("calibration")
    return arv.umpire_model().fit(X, y), report, oof


# ---------------------------------------------------------------- Phase 3: run values

def run_expectancy(root: Path, season: int) -> tuple[RunExpectancy, dict]:
    rows = load_rows(root, "pitches", season, columns=RE_COLUMNS)
    events = load_rows(root, "events", season)
    accepted, quality = reliable_halves(rows, events)
    re = RunExpectancy(accepted)
    return re, {"pitches": len(rows), "accepted_pitches": len(accepted), "excluded_halves": quality["excluded_halves"],
                "re_complete_halves": quality["re_complete_halves"], **re.diagnostics}


def states(df: pd.DataFrame) -> list:
    """swing_take._state tuples (bases, outs, balls, strikes); None for a missing or impossible state."""
    keys = ("base_state_code_before", "outs_before", "balls_before", "strikes_before")
    values = df[list(keys)].astype("Int64").to_numpy(dtype=object, na_value=None)
    return [_state({k: (None if v is None else int(v)) for k, v in zip(keys, row)}, "before") for row in values]


def region(margin: np.ndarray) -> np.ndarray:
    out = np.full(margin.shape, "", dtype=object)
    for low, high, name in REGION_BANDS:
        out[(margin > low) & (margin <= high)] = name
    return out


def count_bucket(df: pd.DataFrame) -> pd.Series:
    return df["balls_before"].astype(int).astype(str) + "-" + df["strikes_before"].astype(int).astype(str)


def player_tables(rv: pd.DataFrame, role: str) -> tuple[list[dict], dict]:
    """Per-player ABS RV in the role's own sign, with game-bootstrap 90% intervals.

    ``relative`` subtracts the league mean per take, so a player is compared with the league-wide
    ABS shift rather than credited with it. The bootstrap covers sampling only, not model error.
    """
    id_col, name_col = f"{role}_id", f"{role}_name"
    sign = 1.0 if role == "batter" else -1.0
    league_mean = sign * rv["abs_rv_batter"].mean()
    rv = rv.assign(value=sign * rv["abs_rv_batter"], calls=sign * rv["call_shift"],
                   relative=sign * rv["abs_rv_batter"] - league_mean,
                   shift_in=sign * rv["shift_in_1cm"], shift_out=sign * rv["shift_out_1cm"])
    players, details = [], {}
    for pid, part in rv.groupby(id_col):
        n = len(part)
        total, relative = float(part["value"].sum()), float(part["relative"].sum())
        low, high = arv.bootstrap_by_game(part["value"], part["game_id"], BOOTSTRAP_REPS)
        rel_low, rel_high = arv.bootstrap_by_game(part["relative"], part["game_id"], BOOTSTRAP_REPS)
        players.append({
            "id": pid, "name": part[name_col].iloc[-1], "takes": n, "games": int(part["game_id"].nunique()),
            "abs_rv": round(total, 2), "abs_rv_per_1000": round(1000 * total / n, 2),
            "ci90_low": round(low, 2), "ci90_high": round(high, 2),
            "relative_rv": round(relative, 2), "relative_per_1000": round(1000 * relative / n, 2),
            "relative_ci90_low": round(rel_low, 2), "relative_ci90_high": round(rel_high, 2),
            "favorable_calls": round(float(part["calls"].clip(lower=0).sum()), 1),
            "unfavorable_calls": round(float(-part["calls"].clip(upper=0).sum()), 1),
            "net_calls": round(float(part["calls"].sum()), 1),
            # Assumed-error scenarios (not observed errors): independent N(0, 1 cm) per pitch, and every
            # boundary moved 1 cm inward / outward.
            "noise_sd_1cm": round(float(np.sqrt(part["noise_var_1cm"].sum())), 2),
            "shift_in_1cm": round(float(part["shift_in"].sum()), 2),
            "shift_out_1cm": round(float(part["shift_out"].sum()), 2),
            "qualified": n >= QUALIFIED_TAKES[role],
        })
        if n >= DETAIL_MIN_TAKES:
            details[pid] = {key: breakdown(part, key) for key in ("pitch_group", "count", "region", "edge", "stadium")}
    players.sort(key=lambda p: -p["relative_rv"])
    return players, details


def breakdown(part: pd.DataFrame, key: str) -> list[dict]:
    rows = []
    for name, group in part.groupby(key):
        if name == "":
            continue
        rows.append({"group": str(name), "takes": int(len(group)), "abs_rv": round(float(group["value"].sum()), 3),
                     "net_calls": round(float(group["calls"].sum()), 1)})
    return sorted(rows, key=lambda r: -abs(r["abs_rv"]))


def split_half_reliability(rv: pd.DataFrame, role: str) -> dict:
    """Correlation of per-1000 ABS RV between odd and even games for players with enough takes in both halves."""
    id_col = f"{role}_id"
    sign = 1.0 if role == "batter" else -1.0
    games = {g: i for i, g in enumerate(sorted(rv["game_id"].unique()))}
    half = rv["game_id"].map(games) % 2
    agg = rv.assign(value=sign * rv["abs_rv_batter"], half=half).groupby([id_col, "half"])["value"].agg(["sum", "size"]).unstack()
    agg = agg[(agg[("size", 0)] >= 150) & (agg[("size", 1)] >= 150)]
    if len(agg) < 10:
        return {"players": int(len(agg)), "pearson_r": None}
    a, b = 1000 * agg[("sum", 0)] / agg[("size", 0)], 1000 * agg[("sum", 1)] / agg[("size", 1)]
    r = float(np.corrcoef(a, b)[0, 1])
    return {"players": int(len(agg)), "pearson_r": r4(r), "spearman_brown": r4(2 * r / (1 + r)) if r > -1 else None}


# ---------------------------------------------------------------- Phase 2: tracking audit

def trackman_pairs(root: Path, seasons=(2022, 2023, 2024)) -> dict[int, pd.DataFrame]:
    path = root / "analysis/movement_calibration/match_trackman.py"
    spec = importlib.util.spec_from_file_location("match_trackman", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {season: module.match_season(root, season, 3.0)[0] for season in seasons}


def gap_summary(diff: pd.Series) -> dict:
    diff = diff.dropna()
    if diff.empty:
        return {"n": 0}
    return {"n": int(diff.size), "median": r4(diff.median()), "mean": r4(diff.mean()),
            "mad": r4((diff - diff.median()).abs().median()), "p90_abs": r4(diff.abs().quantile(.9))}


# Pitch types with many published seam-shifted-wake examples. A hypothesis label from the literature,
# not a classification of any pitch: no spin axis or spin efficiency is available.
SSW_LITERATURE_CODES = ("FT", "SI", "CH", "FS", "ST")


def cluster_mean_ci(values, clusters, reps: int = 200, seed: int = arv.RANDOM_STATE) -> tuple[float, float]:
    """90% percentile interval of the mean, resampling clusters (pitchers) with replacement."""
    values, clusters = np.asarray(values, float), np.asarray(clusters)
    _, index = np.unique(clusters, return_inverse=True)
    sums, counts = np.bincount(index, weights=values), np.bincount(index).astype(float)
    weights = np.random.default_rng(seed).multinomial(sums.size, np.full(sums.size, 1 / sums.size), size=reps)
    means = (weights @ sums) / (weights @ counts)
    return r4(np.quantile(means, .05)), r4(np.quantile(means, .95))


def scaled_movement_residuals(m: pd.DataFrame) -> dict:
    """VB - (a + b * TM) per movement component, then by pitch type.

    VB measures movement from 50 ft to the front of the plate and TrackMan from release, so VB magnitudes
    are a fraction of TrackMan's. HB residuals are reported arm-side positive. The season-wide linear fit removes that definitional scale; what remains
    by pitch type is the part a common scale cannot explain.
    """
    out = {}
    for component, (vb, tm) in {"ivb": ("vertical_movement_cm", "induced_vert_break"), "hb": ("horizontal_movement_cm", "tm_hb")}.items():
        part = m.dropna(subset=[vb, tm])
        slope, intercept = np.polyfit(part[tm], part[vb], 1)
        residual = part[vb] - (intercept + slope * part[tm])
        if component == "hb":
            # Fitted in the catcher view (camera offsets live there), read arm-side positive so RHP and LHP
            # residuals of the same pitch type do not cancel.
            residual = residual * part["pitcher_hand"].map({"Right": -1.0, "Left": 1.0})
            residual = residual.dropna()
            part = part.loc[residual.index]
        rows = []
        for key, mask in [(code, part["pitch_code"].eq(code)) for code in sorted(part["pitch_code"].unique()) if code] + \
                         [("SSW 문헌 구종", part["pitch_code"].isin(SSW_LITERATURE_CODES)), ("기타 구종", ~part["pitch_code"].isin(SSW_LITERATURE_CODES))]:
            if mask.sum() < 200:
                continue
            low, high = cluster_mean_ci(residual[mask], part.loc[mask, "pitcher_id"])
            rows.append({"group": key, "n": int(mask.sum()), "pitchers": int(part.loc[mask, "pitcher_id"].nunique()),
                         "mean": r4(residual[mask].mean()), "ci90_low": low, "ci90_high": high,
                         "mad": r4((residual[mask] - residual[mask].median()).abs().median())})
        out[component] = {"slope": r4(slope), "intercept": r4(intercept), "residual_sd": r4(residual.std()), "by_group": rows}
    return out


def tracking_audit(pairs: dict[int, pd.DataFrame], frames: dict[int, pd.DataFrame]) -> dict:
    from .pitch_types import pitch_code
    audit = {"trackman_vs_pts": {}, "reported_vs_trajectory": {}, "sensitivity": {}}
    for season, m in pairs.items():
        m = m.copy()
        m["pitch_code"] = [pitch_code(r) for r in m[["pitch_id", "pitch_type_code", "pitch_type_kr"]].to_dict("records")]
        m["tm_hb"] = -m["horz_break"]  # TrackMan sign to the VB catcher view
        m["d_hb"] = m["horizontal_movement_cm"] - m["tm_hb"]
        m["d_ivb"] = m["vertical_movement_cm"] - m["induced_vert_break"]
        m["d_speed"] = m["velocity_kmh"] - m["rel_speed"]
        m["d_rel_height"] = m["release_height_cm"] - 100 * m["rel_height"]
        entry = {"pairs": int(len(m)), "overall": {k: gap_summary(m[k]) for k in ("d_hb", "d_ivb", "d_speed", "d_rel_height")}}
        for key in ("pitch_code", "stadium"):
            entry[f"by_{key}"] = [{"group": str(g), **{k: gap_summary(part[k]) for k in ("d_hb", "d_ivb", "d_speed", "d_rel_height")}}
                                  for g, part in sorted(m.groupby(key), key=lambda item: -len(item[1])) if g and len(part) >= 200]
        entry["scaled_residual"] = scaled_movement_residuals(m)
        entry["spin_rate_by_pitch_code"] = {str(g): r4(part["spin_rate"].median()) for g, part in m.groupby("pitch_code") if g and len(part) >= 200}
        audit["trackman_vs_pts"][str(season)] = entry
    for season in ABS_SEASONS:
        df = frames[season]
        ok = df[df["take"] & (df["recon_status"] == "ok")]
        # Reported px (middle plane) and pz (front plane) against the trajectory at the same plane, in cm.
        # VB rounds px/pz to 0.01 ft, so up to 0.15 cm is rounding, not tracking error.
        dx = df["px"] * az.CM_PER_FOOT - df["x_mid_cm"]
        dz = df["pz"] * az.CM_PER_FOOT - df["z_front_cm"]
        audit["reported_vs_trajectory"][str(season)] = {
            "overall": {"x": gap_summary(dx), "z": gap_summary(dz), "beyond_1cm": int(((dx.abs() > 1) | (dz.abs() > 1)).sum())},
            "by_pitch_code": [{"group": g, "x": gap_summary(dx[part.index]), "z": gap_summary(dz[part.index])}
                              for g, part in sorted(df.groupby("pitch_code"), key=lambda item: -len(item[1])) if g]}
        audit["sensitivity"][str(season)] = {
            str(sigma): {
                "expected_flip_share": r4(az.flip_probability(ok["zone_margin_cm"], sigma).mean()),
                "by_pitch_code": {g: r4(az.flip_probability(part["zone_margin_cm"], sigma).mean())
                                  for g, part in ok.groupby("pitch_code") if g},
                "by_edge": {g: r4(az.flip_probability(part["zone_margin_cm"], sigma).mean())
                            for g, part in ok.groupby("binding_edge") if g},
                # Every boundary moved by sigma: share of takes whose reconstructed call would change.
                "systematic_inward_share": r4(((ok["zone_margin_cm"] >= 0) & (ok["zone_margin_cm"] < sigma)).mean()),
                "systematic_outward_share": r4(((ok["zone_margin_cm"] < 0) & (ok["zone_margin_cm"] >= -sigma)).mean()),
            } for sigma in ASSUMED_ERROR_CM}
    return audit


# ---------------------------------------------------------------- Phase 4: zone map

def zone_grid(df: pd.DataFrame, heights: pd.Series, p_umpire: pd.Series | None) -> dict:
    x0, x1, dx = GRID_X_CM
    z0, z1, dz = GRID_Z_SHARE
    nx, nz = int(round((x1 - x0) / dx)), int(round((z1 - z0) / dz))
    share = df["z_mid_cm"] / df["batter_id"].map(heights).astype(float)
    ix = np.floor((df["x_mid_cm"] - x0) / dx)
    iz = np.floor((share - z0) / dz)
    inside = ix.between(0, nx - 1) & iz.between(0, nz - 1)
    strikes = df["strikes_before"].astype(float)
    filters = {}
    for stance in STANCE_FILTERS:
        for count in COUNT_FILTERS:
            for group in GROUP_FILTERS:
                mask = inside.copy()
                if stance != "all":
                    mask &= df["batter_stance"].eq(stance)
                if count != "all":
                    mask &= strikes.eq(int(count[1]))
                if group != "all":
                    mask &= df["pitch_group"].eq(group)
                part = pd.DataFrame({"cell": (ix[mask] * nz + iz[mask]).astype(int), "k": df.loc[mask, "recorded_strike"]})
                if p_umpire is not None:
                    part["p"] = p_umpire[mask]
                agg = part.groupby("cell").agg(n=("k", "size"), k=("k", "sum"), **({"p": ("p", "sum")} if p_umpire is not None else {}))
                cells = [[int(c), int(r.n), int(r.k)] + ([round(float(r.p), 2)] if p_umpire is not None else []) for c, r in agg.iterrows()]
                filters[f"{stance}|{count}|{group}"] = cells
    return {"x": {"start": x0, "step": dx, "bins": nx}, "z_share": {"start": z0, "step": dz, "bins": nz},
            "fields": ["cell", "takes", "strikes"] + (["umpire_expected_strikes"] if p_umpire is not None else []),
            "takes": int(inside.sum()), "takes_outside_grid_or_unknown": int((~inside).sum()), "filters": filters}


# ---------------------------------------------------------------- build

def build(root: Path, skip_trackman: bool = False) -> dict:
    batter_hands = load_batter_hands(root)
    frames = {season: load_pitches(root, season, batter_hands) for season in SEASONS}
    for df in frames.values():
        add_planes(df)
        df["take"] = is_take(df)
        df["recorded_strike"] = (df["pitch_call_code"] == "T").astype(float)
    heights, height_audit = height_table(frames)
    for season in ABS_SEASONS:
        reconstruct(frames[season], season)
    reconstruction, mismatches = reconstruction_report(frames)

    hands = pitcher_hands(root)
    train_parts, coverage = [], {}
    for season in UMPIRE_SEASONS:
        df = frames[season]
        takes = df[df["take"]]
        features = umpire_features(takes, heights, hands)
        keep = complete_features(features)
        coverage[str(season)] = {"takes": int(len(takes)), "with_height_and_location": int(keep.sum()),
                                 "share": r4(keep.mean())}
        part = features[keep].copy()
        part["y"] = takes.loc[keep, "recorded_strike"].astype(int).to_numpy()
        part["game_id"] = takes.loc[keep, "game_id"].to_numpy()
        part["season_id"] = season
        part["batter_id"] = takes.loc[keep, "batter_id"].to_numpy()
        # Diagnostic subset only: within 10 cm of the 2024 ABS zone edge on the front plane.
        top = az.ABS_RULES[2024].top_ratio * part["height_cm"]
        bottom = az.ABS_RULES[2024].bottom_ratio * part["height_cm"]
        part["boundary"] = ((part["z_front_cm"] - top).abs() <= 10) | ((part["z_front_cm"] - bottom).abs() <= 10) | \
                           ((part["x_front_cm"].abs() - 27).abs() <= 10)
        train_parts.append(part)
    train = pd.concat(train_parts)
    model, model_report, oof = fit_umpire(train)
    train["oof"] = oof
    model_report["training_coverage"] = coverage
    model_report["features"] = list(arv.UMPIRE_FEATURES)
    model_report["counterfactual_season_value"] = arv.COUNTERFACTUAL_SEASON

    rv_frames, re_report, season_summary = {}, {}, {}
    for season in ABS_SEASONS:
        df = frames[season]
        takes = df[df["take"] & (df["recon_status"] == "ok")].copy()
        features = umpire_features(takes, heights, hands, arv.COUNTERFACTUAL_SEASON)
        keep = complete_features(features)
        takes, features = takes[keep], features[keep]
        takes["p_umpire"] = model.predict_proba(features)[:, 1]
        takes["p_umpire_2022"] = model.predict_proba(features.assign(season=2022.0))[:, 1]
        re, re_report[str(season)] = run_expectancy(root, season)
        rv_ball, rv_strike = arv.call_values(re, states(takes))
        takes["rv_ball"], takes["rv_strike"] = rv_ball, rv_strike
        takes = takes[np.isfinite(rv_ball) & np.isfinite(rv_strike)]
        takes["abs_rv_batter"] = arv.abs_run_value(takes["p_umpire"], takes["recorded_strike"], takes["rv_ball"], takes["rv_strike"])
        takes["abs_rv_batter_2022"] = arv.abs_run_value(takes["p_umpire_2022"], takes["recorded_strike"], takes["rv_ball"], takes["rv_strike"])
        takes["call_shift"] = arv.expected_call_change(takes["p_umpire"], takes["recorded_strike"])
        # Assumed-error scenarios. D = RV(ball) - RV(strike); a flip moves the batter's value by +-D.
        gap = (takes["rv_ball"] - takes["rv_strike"]).to_numpy()
        margin = takes["zone_margin_cm"].to_numpy()
        flip = az.flip_probability(margin, 1.0)
        takes["noise_var_1cm"] = flip * (1 - flip) * gap ** 2
        abs_call = margin >= 0
        takes["shift_in_1cm"] = np.where(abs_call & (margin < 1.0), gap, 0.0)       # strike -> ball helps the batter
        takes["shift_out_1cm"] = np.where(~abs_call & (margin >= -1.0), -gap, 0.0)  # ball -> strike hurts the batter
        takes["count"] = count_bucket(takes)
        takes["region"] = region(takes["zone_margin_cm"].to_numpy())
        takes["edge"] = takes["binding_edge"].fillna("")
        rv_frames[season] = takes
        season_summary[str(season)] = {
            "takes": int(len(takes)), "excluded_takes": int(df["take"].sum() - len(takes)),
            "recorded_strike_rate": r4(takes["recorded_strike"].mean()), "umpire_expected_strike_rate": r4(takes["p_umpire"].mean()),
            "league_abs_rv_batter": round(float(takes["abs_rv_batter"].sum()), 2),
            "league_abs_rv_batter_per_1000": round(float(1000 * takes["abs_rv_batter"].mean()), 3),
            "league_abs_rv_batter_2022_umpire": round(float(takes["abs_rv_batter_2022"].sum()), 2),
            "by_region": breakdown(takes.assign(value=takes["abs_rv_batter"], calls=takes["call_shift"]), "region"),
            "by_edge": breakdown(takes.assign(value=takes["abs_rv_batter"], calls=takes["call_shift"]), "edge"),
            "by_count": breakdown(takes.assign(value=takes["abs_rv_batter"], calls=takes["call_shift"]), "count"),
            "by_pitch_group": breakdown(takes.assign(value=takes["abs_rv_batter"], calls=takes["call_shift"]), "pitch_group"),
        }

    leaderboards, details, reliability = {}, {}, {}
    scopes = {str(s): rv_frames[s] for s in ABS_SEASONS}
    scopes["2024-2026"] = pd.concat(rv_frames.values())
    for scope, rv in scopes.items():
        for role in ("batter", "pitcher"):
            players, detail = player_tables(rv, role)
            leaderboards[f"{scope}|{role}"] = players
            details[f"{scope}|{role}"] = detail
            reliability[f"{scope}|{role}"] = split_half_reliability(rv, role)
    for role in ("batter", "pitcher"):
        a = pd.DataFrame(leaderboards[f"2024|{role}"]).set_index("id")
        b = pd.DataFrame(leaderboards[f"2025|{role}"]).set_index("id")
        both = a.join(b, lsuffix="_a", rsuffix="_b", how="inner")
        both = both[(both["takes_a"] >= QUALIFIED_TAKES[role]) & (both["takes_b"] >= QUALIFIED_TAKES[role])]
        reliability[f"2024_to_2025|{role}"] = {"players": int(len(both)),
                                               "pearson_r": r4(np.corrcoef(both["abs_rv_per_1000_a"], both["abs_rv_per_1000_b"])[0, 1]) if len(both) > 10 else None}
        sens = scopes["2024-2026"]
        sign = 1.0 if role == "batter" else -1.0
        main_ = sens.groupby(f"{role}_id")["abs_rv_batter"].sum() * sign
        alt = sens.groupby(f"{role}_id")["abs_rv_batter_2022"].sum() * sign
        reliability[f"umpire_2022_vs_2023|{role}"] = {"pearson_r": r4(np.corrcoef(main_, alt)[0, 1])}

    # Did batters the umpires already favoured (balls on pitches the average umpire calls strikes, out of fold)
    # lose under ABS? The counterfactual is the league-average umpire, so batter-specific treatment is not in it.
    umpire_era = train.groupby("batter_id").agg(n=("y", "size"), favour=("oof", "sum"), strikes=("y", "sum"))
    umpire_era = umpire_era[umpire_era["n"] >= QUALIFIED_TAKES["batter"]]
    umpire_era["favour_per_1000"] = 1000 * (umpire_era["favour"] - umpire_era["strikes"]) / umpire_era["n"]
    abs_era = pd.DataFrame(leaderboards["2024-2026|batter"]).set_index("id")
    linked = umpire_era.join(abs_era[abs_era["qualified"]], how="inner")
    reliability["umpire_era_favour_vs_abs_relative|batter"] = {
        "players": int(len(linked)),
        "pearson_r": r4(np.corrcoef(linked["favour_per_1000"], linked["relative_per_1000"])[0, 1]) if len(linked) > 10 else None}

    pairs = None if skip_trackman else trackman_pairs(root)
    tracking = tracking_audit(pairs or {}, frames)
    if skip_trackman:
        previous = root / OUT / "tracking_audit.json"
        if previous.exists():
            tracking["trackman_vs_pts"] = json.loads(previous.read_text(encoding="utf-8"))["trackman_vs_pts"]

    grids = {}
    for season in SEASONS:
        df = frames[season]
        takes = df[df["take"]]
        if season in ABS_SEASONS:
            rv = rv_frames[season]
            grids[season] = zone_grid(rv, heights, rv["p_umpire"])
        else:
            grids[season] = zone_grid(takes, heights, None)

    return {"heights": height_audit, "reconstruction": reconstruction, "mismatches": mismatches, "umpire_model": model_report,
            "run_expectancy": re_report, "season_summary": season_summary, "leaderboards": leaderboards, "details": details,
            "reliability": reliability, "tracking": tracking, "grids": grids}


def write_outputs(root: Path, result: dict) -> None:
    out, web = root / OUT, root / WEB_OUT
    out.mkdir(parents=True, exist_ok=True)
    web.mkdir(parents=True, exist_ok=True)
    common = {"schema_version": 1, "status": STATUS}
    write_json(out / "data_audit.json", {**common, "heights": result["heights"]}, compact=False)
    write_json(out / "reconstruction.json", {**common, **result["reconstruction"]}, compact=False)
    result["mismatches"].round(3).to_csv(out / "reconstruction_mismatches.csv", index=False)
    write_json(out / "umpire_model.json", {**common, **result["umpire_model"], "run_expectancy": result["run_expectancy"]}, compact=False)
    write_json(out / "abs_rv_summary.json", {**common, "seasons": result["season_summary"], "reliability": result["reliability"]}, compact=False)
    write_json(out / "tracking_audit.json", {**common, **result["tracking"]}, compact=False)
    for key, players in result["leaderboards"].items():
        scope, role = key.split("|")
        pd.DataFrame(players).to_csv(out / f"abs_rv_{role}_{scope}.csv", index=False)

    write_json(web / "index.json", {
        **common, "seasons": list(SEASONS), "abs_seasons": list(ABS_SEASONS), "scopes": [str(s) for s in ABS_SEASONS] + ["2024-2026"],
        "rules": {str(s): {"top_ratio": r.top_ratio, "bottom_ratio": r.bottom_ratio, "width_cm": r.width_cm,
                           "back_bottom_offset_cm": r.back_bottom_offset_cm} for s, r in az.ABS_RULES.items()},
        "ball_radius_cm": az.BALL_RADIUS_CM, "qualified_takes": QUALIFIED_TAKES,
        "filters": {"stance": STANCE_FILTERS, "count": COUNT_FILTERS, "group": GROUP_FILTERS},
        "season_summary": result["season_summary"], "reliability": result["reliability"],
        "model": {k: result["umpire_model"][k] for k in ("game_grouped_5fold", "temporal_2022_to_2023", "training_coverage", "features")},
    })
    for season, grid in result["grids"].items():
        write_json(web / f"zone_map_{season}.json", {**common, "season": season, **grid})
    recon = result["reconstruction"]
    write_json(web / "tracking.json", {**common, "reconstruction": {
        "seasons": {s: {k: v[k] for k in ("takes", "status", "overall", "by_edge", "by_pitch_code", "by_stadium", "rule_change_vs_2024")}
                    for s, v in recon["seasons"].items()},
        "pooled": recon["pooled_2024_2026"], "radius_scan": recon["radius_scan"]}, **result["tracking"]})
    for key, players in result["leaderboards"].items():
        scope, role = key.split("|")
        write_json(web / f"players_{role}_{scope}.json", {**common, "scope": scope, "role": role, "players": players,
                                                          "details": result["details"][key]})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--skip-trackman", action="store_true", help="reuse trackman_vs_pts from the previous tracking_audit.json")
    args = parser.parse_args()
    write_outputs(args.root, build(args.root, args.skip_trackman))


if __name__ == "__main__":
    main()
