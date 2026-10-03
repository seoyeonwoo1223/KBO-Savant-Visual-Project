"""Build Baseball Savant-style pitcher arsenal profiles from canonical curated pitches.

Movement is corrected by movement_calibration (stadium-day and plate-location terms,
validated against TrackMan). The seasonal park-adjustment workbook is still read by the
SBJ p_swing path through plate_decision_v1, not here.
"""

from __future__ import annotations

from collections import defaultdict
import math
from pathlib import Path
from statistics import fmean, median

from .batter_stance import load_batter_hands, resolved_batter_stance
from .curated import _number, load_rows
from .estimated_arm_angle import season_estimates
from .movement_calibration import calibrate
from .pitch_types import PITCH_NAMES, pitch_code
from .publish import add_catalog_season, write_json, write_shards


CM_PER_INCH = 2.54
FEET_PER_CM = 1 / 30.48
PLATE_HALF_WIDTH_FT = 10 / 12
MIN_PERCENTILE_PITCHES = 50
MAX_MOVEMENT_POINTS = 140
PITCH_COLORS = {
    "FF": "#d62f4b", "FT": "#b9415e", "SI": "#f09a22", "FC": "#8d6d61",
    "SL": "#b5b516", "ST": "#3aa8a6", "CH": "#4bb783", "CU": "#76c8c5", "FS": "#7556b8",
}
TEAM_NAMES = {
    "OB": "두산 베어스", "SS": "삼성 라이온즈", "WO": "키움 히어로즈", "LT": "롯데 자이언츠", "HH": "한화 이글스",
    "HT": "KIA 타이거즈", "SK": "SSG 랜더스", "LG": "LG 트윈스", "NC": "NC 다이노스", "KT": "KT 위즈",
}
PROFILE_SCHEMA_VERSION = 4
PITCH_ARSENAL_SEASONS = (2022, 2023, 2024, 2025, 2026)
# A pitch type thrown at most MINOR_MAX_PITCHES times or under MINOR_USAGE_PCT of a pitcher's
# pitches is shown inside the nearest main pitch type of the same pitcher when its median
# velocity, corrected HB and IVB each fall within MERGE_TOLERANCE of that type's medians and its
# median location within LOCATION_TOLERANCE_FT. Fixed tolerances, not the main type's own
# spread: a broad main type (a slider thrown both ways) must not absorb a distinct pitch. This
# is a display grouping only: curated pitch_type and every model input keep the original label.
MINOR_MAX_PITCHES = 10
MINOR_USAGE_PCT = 5.0
MERGE_TOLERANCE = {"velocity": 5.0, "hb": 8.0, "ivb": 8.0}   # km/h, cm, cm
LOCATION_TOLERANCE_FT = 1.5



METHOD = {
    "movement": "corrected HB and IVB; measured minus plate-location term minus stadium-day effect from a pitcher x pitch type + stadium x day fit",
    "minor_pitch_types": (f"types with at most {MINOR_MAX_PITCHES} pitches or under {MINOR_USAGE_PCT:g}% usage are shown inside the "
                          f"nearest main type of the same pitcher when median velocity is within {MERGE_TOLERANCE['velocity']:g} km/h, "
                          f"corrected HB and IVB each within {MERGE_TOLERANCE['hb']:g} cm and median location within "
                          f"{LOCATION_TOLERANCE_FT:g} ft (display only; merged_from keeps the original labels); otherwise they stay "
                          "separate with minor=true"),
    "interval": "central 75% (12.5th to 87.5th percentile)",
    "units": {"velocity": "km/h", "movement": "in"},
    "release": "hRel/vRel are the normalized y=50 ft release_x_50/release_z_50 values",
    "eaa": "frozen eAA-v1: pitcher-season mean from canonical 55ft trajectories and verified height; model reference envelope, KBO accuracy unvalidated; unseen stadium bounds withheld",
    "zone": "abs(px) <= 10/12 ft and sz_bottom <= pz <= sz_top",
    "rates": {
        "zone_pct": "in-zone pitches / pitches with valid ABS location",
        "chase_pct": "swings outside the ABS zone / pitches outside the ABS zone",
        "swstr_pct": "swings without contact / all pitches",
    },
    "percentiles": f"same pitch type, pitcher-pitch groups with at least {MIN_PERCENTILE_PITCHES} pitches",
    "percentile_scope": f"velocity_kmh is graded for every group; the rate metrics only for groups with at least {MIN_PERCENTILE_PITCHES} pitches",
}
RATE_METRICS = ("zone_pct", "chase_pct", "swstr_pct")


def _season(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _pitcher_team(row: dict) -> str:
    game_id = str(row.get("game_id") or "")
    if len(game_id) < 12:
        return ""
    code = game_id[10:12] if row.get("inning_half") == "top" else game_id[8:10]
    return TEAM_NAMES.get(code, "")


def _quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _summary(values: list[float], digits: int = 1) -> dict | None:
    if not values:
        return None
    return {
        "average": round(fmean(values), digits),
        "low_75": round(_quantile(values, 0.125), digits),
        "high_75": round(_quantile(values, 0.875), digits),
    }


def _histogram(values: list[float]) -> dict | None:
    """Return compact 1 km/h bins for the browser-side velocity ridgeline."""
    if not values:
        return None
    low, high = math.floor(min(values)), math.ceil(max(values))
    centers = list(range(low, high + 1))
    counts = [0] * len(centers)
    for value in values:
        index = min(len(counts) - 1, max(0, int(math.floor(value - low + 0.5))))
        counts[index] += 1
    return {"start": low, "step": 1, "counts": counts}


def _sample_points(values: list[tuple[float, float, float, float]]) -> dict:
    """Evenly sample paired raw/adjusted movement points for a lightweight scatter."""
    if not values:
        return {"raw": [], "adjusted": []}
    if len(values) <= MAX_MOVEMENT_POINTS:
        sampled = values
    else:
        sampled = [values[round(index * (len(values) - 1) / (MAX_MOVEMENT_POINTS - 1))]
                   for index in range(MAX_MOVEMENT_POINTS)]
    return {
        "raw": [[round(item[0], 2), round(item[1], 2)] for item in sampled],
        "adjusted": [[round(item[2], 2), round(item[3], 2)] for item in sampled],
    }


def _rate(numerator: int, denominator: int) -> float | None:
    return round(100 * numerator / denominator, 1) if denominator else None


def _rates(bucket: dict) -> dict:
    return {
        "zone_pct": _rate(bucket["in_zone"], bucket["location_n"]),
        "chase_pct": _rate(bucket["chase_swings"], bucket["out_zone"]),
        "swstr_pct": _rate(bucket["swstr"], bucket.get("n", bucket.get("pitches", 0))),
    }


def _percentile(value: float | None, population: list[float]) -> int | None:
    if value is None or not population:
        return None
    below = sum(item < value for item in population)
    tied = sum(item == value for item in population)
    return round(100 * (below + 0.5 * tied) / len(population))


def _profile(samples: list[dict]) -> dict:
    result = {}
    for feature in ("velocity", "hb", "ivb", "px", "pz"):
        values = [item[feature] for item in samples if item[feature] is not None]
        if values:
            result[feature] = median(values)
    return result


def _distance(minor: dict, main: dict) -> float | None:
    """Largest gap as a share of its tolerance; at most 1 means every check passes."""
    if any(feature not in minor or feature not in main for feature in MERGE_TOLERANCE):
        return None
    gaps = [abs(minor[feature] - main[feature]) / tolerance for feature, tolerance in MERGE_TOLERANCE.items()]
    if all(feature in minor and feature in main for feature in ("px", "pz")):
        gaps.append(math.hypot(minor["px"] - main["px"], minor["pz"] - main["pz"]) / LOCATION_TOLERANCE_FT)
    return max(gaps)


def _minor_merges(samples: dict[str, dict[str, list[dict]]]) -> tuple[dict, set]:
    """Map (pitcher, minor code) -> main code for display; also return unmerged minor types."""
    merges, unmerged = {}, set()
    for pitcher_id, groups in samples.items():
        total = sum(len(items) for items in groups.values())
        minor = {code for code, items in groups.items()
                 if len(items) <= MINOR_MAX_PITCHES or 100 * len(items) / total < MINOR_USAGE_PCT}
        main = [code for code in groups if code not in minor]
        profiles = {code: _profile(items) for code, items in groups.items()}
        for code in minor:
            scored = [(distance, target) for target in main
                      if (distance := _distance(profiles[code], profiles[target])) is not None]
            best = min(scored, default=None)
            if best is not None and best[0] <= 1:
                merges[(pitcher_id, code)] = best[1]
            elif main:
                unmerged.add((pitcher_id, code))
    return merges, unmerged


def _throws(release_x: list[float]) -> str:
    if not release_x:
        return ""
    return "R" if median(release_x) < 0 else "L"

def _eligible_rows(canonical_pitches: list[dict], season: int) -> list[tuple[dict, str, str, str]]:
    """(row, pitch code, pitcher id, pitcher name) for parsed, labelled pitches of the season."""
    rows = []
    for row in canonical_pitches:
        if _season(row.get("season")) != season or str(row.get("parse_status") or "") != "ok":
            continue
        code = pitch_code(row)
        pitcher_name = str(row.get("pitcher_name") or "").strip()
        if code and pitcher_name:
            rows.append((row, code, str(row.get("pitcher_id") or pitcher_name).strip(), pitcher_name))
    return rows


def _merge_samples(rows: list[tuple], movement: list[tuple]) -> dict[str, dict[str, list[dict]]]:
    samples: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for (row, code, pitcher_id, _), (hb, ivb) in zip(rows, movement):
        samples[pitcher_id][code].append({"velocity": _number(row.get("velocity_kmh")), "hb": hb, "ivb": ivb,
                                          "px": _number(row.get("px")), "pz": _number(row.get("pz"))})
    return samples


def _new_group() -> dict:
    return {
        "n": 0, "velocity": [], "hb": [], "ivb": [], "raw_hb": [], "raw_ivb": [],
        "release_x": [], "release_z": [], "side_counts": {"L": 0, "R": 0},
        "location_n": 0, "in_zone": 0, "out_zone": 0,
        "chase_swings": 0, "swstr": 0,
        "movement_total": 0, "movement_adjusted": 0, "movement_points": [],
        "merged_from": defaultdict(int),
    }


def _new_pitcher(pitcher_id: str, pitcher_name: str) -> dict:
    return {
        "id": pitcher_id, "name": pitcher_name, "release_x": [], "hand_release_x": [],
        "release_z": [], "velocity": [], "pitches": 0,
        "teams": [],
        "side_totals": {"L": 0, "R": 0},
        "location_n": 0, "in_zone": 0, "out_zone": 0,
        "chase_swings": 0, "swstr": 0,
        "groups": defaultdict(_new_group),
    }


def _is_true(value) -> bool:
    return value is True or str(value or "").lower() in {"1", "true"}


def _add_release(pitcher: dict, group: dict, row: dict) -> None:
    velocity = _number(row.get("velocity_kmh"))
    release_x_cm = _number(row.get("release_x_50"))
    release_z_cm = _number(row.get("release_z_50"))
    release_x = release_x_cm * FEET_PER_CM if release_x_cm is not None else None
    release_z = release_z_cm * FEET_PER_CM if release_z_cm is not None else None
    if velocity is not None:
        group["velocity"].append(velocity)
        pitcher["velocity"].append(velocity)
    if release_x is not None:
        pitcher["release_x"].append(release_x)
        group["release_x"].append(abs(release_x))
        if abs(release_x) >= 0.1:
            pitcher["hand_release_x"].append(release_x)
    if release_z is not None:
        pitcher["release_z"].append(release_z)
        group["release_z"].append(release_z)


def _add_location(pitcher: dict, group: dict, row: dict) -> None:
    px, pz = _number(row.get("px")), _number(row.get("pz"))
    sz_top, sz_bottom = _number(row.get("sz_top")), _number(row.get("sz_bottom"))
    swing, contact = _is_true(row.get("is_swing")), _is_true(row.get("is_contact"))
    if swing and not contact:
        pitcher["swstr"] += 1
        group["swstr"] += 1
    if None not in (px, pz, sz_top, sz_bottom):
        in_zone = abs(px) <= PLATE_HALF_WIDTH_FT and sz_bottom <= pz <= sz_top
        for bucket in (pitcher, group):
            bucket["location_n"] += 1
            bucket["in_zone" if in_zone else "out_zone"] += 1
            if not in_zone and swing:
                bucket["chase_swings"] += 1


def _add_movement(group: dict, row: dict, adjusted_hb, adjusted_ivb) -> None:
    raw_hb = _number(row.get("horizontal_movement_cm"))
    raw_ivb = _number(row.get("vertical_movement_cm"))
    if raw_hb is None or raw_ivb is None:
        return
    group["movement_total"] += 1
    if adjusted_hb is None or adjusted_ivb is None:
        return
    point = (raw_hb / CM_PER_INCH, raw_ivb / CM_PER_INCH, adjusted_hb / CM_PER_INCH, adjusted_ivb / CM_PER_INCH)
    group["raw_hb"].append(point[0])
    group["raw_ivb"].append(point[1])
    group["hb"].append(point[2])
    group["ivb"].append(point[3])
    group["movement_points"].append(point)
    group["movement_adjusted"] += 1


def _accumulate(rows: list[tuple], movement: list[tuple], merges: dict, batter_hands: dict[str, str]) -> dict[str, dict]:
    """Per-pitcher totals and per-(display) pitch type groups."""
    pitchers: dict[str, dict] = {}
    for (row, original_code, pitcher_id, pitcher_name), (adjusted_hb, adjusted_ivb) in zip(rows, movement):
        code = merges.get((pitcher_id, original_code), original_code)
        if pitcher_id not in pitchers:
            pitchers[pitcher_id] = _new_pitcher(pitcher_id, pitcher_name)
        pitcher = pitchers[pitcher_id]
        team = _pitcher_team(row)
        if team and team not in pitcher["teams"]:
            pitcher["teams"].append(team)
        group = pitcher["groups"][code]
        if code != original_code:
            group["merged_from"][original_code] += 1
        pitcher["pitches"] += 1
        group["n"] += 1
        _add_release(pitcher, group, row)
        stance = resolved_batter_stance(row, batter_hands)
        if stance in {"L", "R"}:
            pitcher["side_totals"][stance] += 1
            group["side_counts"][stance] += 1
        _add_location(pitcher, group, row)
        _add_movement(group, row, adjusted_hb, adjusted_ivb)
    return pitchers


def _pitch_type_entry(pitcher: dict, code: str, group: dict, minor: bool) -> dict:
    movement_total = group["movement_total"]
    movement_adjusted = group["movement_adjusted"]
    return {
        "code": code,
        "name": PITCH_NAMES[code],
        "color": PITCH_COLORS[code],
        "n": group["n"],
        "usage": round(group["n"] / pitcher["pitches"] * 100, 1),
        "usage_by_batter": {
            side: {
                "n": group["side_counts"][side],
                "usage": _rate(group["side_counts"][side], pitcher["side_totals"][side]),
            } for side in ("L", "R")
        },
        "velocity_kmh": _summary(group["velocity"]),
        "velocity_distribution_kmh": _histogram(group["velocity"]),
        "horizontal_break_in": _summary(group["hb"]),
        "ivb_in": _summary(group["ivb"]),
        "raw_horizontal_break_in": _summary(group["raw_hb"]),
        "raw_ivb_in": _summary(group["raw_ivb"]),
        "movement_points_in": _sample_points(group["movement_points"]),
        "release": {
            "v_rel_ft": _summary(group["release_z"], 2),
            "h_rel_ft": _summary(group["release_x"], 2),
        },
        "rates": _rates(group),
        "percentiles": {"velocity_kmh": None, "zone_pct": None, "chase_pct": None, "swstr_pct": None},
        "percentile_qualified": group["n"] >= MIN_PERCENTILE_PITCHES,
        "movement_n": movement_adjusted,
        "movement_total_n": movement_total,
        "movement_coverage": round(movement_adjusted / movement_total * 100, 1) if movement_total else 0.0,
        # Display grouping: original labels folded into this row, and unmerged small types.
        "merged_from": [{"code": source, "name": PITCH_NAMES[source], "n": count}
                        for source, count in sorted(group["merged_from"].items(), key=lambda item: -item[1])],
        "minor": minor,
    }


def _profile_payload(season: int, pitcher_id: str, pitcher: dict, eaa: dict, unmerged: set) -> dict:
    groups = sorted(pitcher["groups"].items(), key=lambda item: item[1]["n"], reverse=True)
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "season": season,
        "source": {
            "dataset": f"data/curated/pitches/season={season}",
            "movement_calibration": "src/visualbaseball/movement_calibration.py (TrackMan-validated, analysis/movement_calibration)",
        },
        "method": METHOD,
        "player": {
            "id": pitcher_id, "name": pitcher["name"], "throws": _throws(pitcher["hand_release_x"] or pitcher["release_x"]),
            "team": " · ".join(pitcher["teams"]),
            "pitches": pitcher["pitches"], "batter_side_pitches": pitcher["side_totals"],
        },
        "overall": {
            "n": pitcher["pitches"],
            "eaa": eaa.get(pitcher_id),
            "velocity_kmh": _summary(pitcher["velocity"]),
            "release": {
                "v_rel_ft": _summary(pitcher["release_z"], 2),
                "h_rel_ft": _summary([abs(value) for value in pitcher["release_x"]], 2),
            },
            "rates": _rates(pitcher),
            "percentiles": {"velocity_kmh": None, "zone_pct": None, "chase_pct": None, "swstr_pct": None},
            "percentile_qualified": pitcher["pitches"] >= MIN_PERCENTILE_PITCHES,
        },
        "pitch_types": [_pitch_type_entry(pitcher, code, group, (pitcher_id, code) in unmerged) for code, group in groups],
    }


def _collect_population(population: dict[str, list], entry: dict) -> None:
    if not entry["percentile_qualified"]:
        return
    if entry["velocity_kmh"]:
        population["velocity_kmh"].append(entry["velocity_kmh"]["average"])
    for metric in RATE_METRICS:
        if entry["rates"][metric] is not None:
            population[metric].append(entry["rates"][metric])


def _grade(entry: dict, population: dict[str, list]) -> None:
    # Velocity is graded for every group, including those under MIN_PERCENTILE_PITCHES: a mean
    # speed is stable at a handful of pitches in a way the rate metrics are not, so withholding it
    # only hid a reliable number.  The population itself still comes from qualified groups only,
    # and `percentile_qualified` stays false so the view keeps flagging the short sample.
    entry["percentiles"]["velocity_kmh"] = (
        _percentile(entry["velocity_kmh"]["average"], population["velocity_kmh"]) if entry["velocity_kmh"] else None
    )
    if entry["percentile_qualified"]:
        entry["percentiles"].update({metric: _percentile(entry["rates"][metric], population[metric]) for metric in RATE_METRICS})


def _assign_percentiles(profiles: list[dict]) -> None:
    """Grade each pitch type against the same type league-wide, and each pitcher overall."""
    by_type: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    overall: dict[str, list] = defaultdict(list)
    for profile in profiles:
        for pitch in profile["pitch_types"]:
            _collect_population(by_type[pitch["code"]], pitch)
        _collect_population(overall, profile["overall"])
    for profile in profiles:
        for pitch in profile["pitch_types"]:
            _grade(pitch, by_type[pitch["code"]])
        _grade(profile["overall"], overall)


def _write_outputs(root: Path, season: int, profiles: list[dict]) -> None:
    output = root / "web" / "data" / "pitch_arsenal" / str(season) / "players"
    shards: dict[str, dict] = defaultdict(dict)
    player_index = []
    for payload in profiles:
        player = payload["player"]
        shard = player["id"][0] if player["id"] and player["id"][0].isdigit() else "other"
        shards[shard][player["id"]] = payload
        player_index.append({
            "id": player["id"], "name": player["name"], "throws": player["throws"],
            "team": player["team"], "pitches": player["pitches"], "file": f"players/{shard}.json",
        })
    write_shards(output, {shard: {"season": season, "players": players} for shard, players in shards.items()})
    write_json(output.parent / "index.json", {"season": season, "players": player_index})
    add_catalog_season(root / "web" / "data" / "pitch_arsenal" / "index.json", season)


def build_pitch_arsenal(root: Path, season: int) -> tuple[int, int]:
    """Export searchable pitcher profiles and compact chart-ready distributions."""
    canonical_pitches = load_rows(root, "pitches", season)
    eaa = season_estimates(root, season, canonical_pitches)
    rows = _eligible_rows(canonical_pitches, season)
    movement = calibrate([item[0] for item in rows], [item[1] for item in rows])
    merges, unmerged = _minor_merges(_merge_samples(rows, movement))
    pitchers = _accumulate(rows, movement, merges, load_batter_hands(root))
    profiles = [_profile_payload(season, pitcher_id, pitcher, eaa, unmerged)
                for pitcher_id, pitcher in sorted(pitchers.items(), key=lambda item: item[1]["name"])]
    _assign_percentiles(profiles)
    _write_outputs(root, season, profiles)
    return len(rows), len(pitchers)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--season", type=int, required=True)
    args = parser.parse_args()
    rows, players = build_pitch_arsenal(Path(args.root).resolve(), args.season)
    print(f"exported {rows} pitches for {players} pitcher arsenal profiles")
