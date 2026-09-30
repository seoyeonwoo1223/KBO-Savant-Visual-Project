"""Build Baseball Savant-style pitcher arsenal profiles from canonical curated pitches.

Movement is corrected by movement_calibration (stadium-day and plate-location terms,
validated against TrackMan). The seasonal park-adjustment workbook is still read by the
SBJ p_swing path through plate_decision_v1, not here.
"""

from __future__ import annotations

from collections import defaultdict
import json
import math
from pathlib import Path
from statistics import fmean, median

from openpyxl import load_workbook

from .curated import load_rows
from .movement_calibration import calibrate


CM_PER_INCH = 2.54
FEET_PER_CM = 1 / 30.48
PLATE_HALF_WIDTH_FT = 10 / 12
MIN_PERCENTILE_PITCHES = 50
MAX_MOVEMENT_POINTS = 140
PITCH_CODES = ("FF", "FT", "SI", "FC", "SL", "ST", "CH", "CU", "FS")
PARK_FACTOR_CODES = ("FF", "SI", "FC", "SL", "CH", "CU", "FS")
PARK_FACTOR_CODE = {"FT": "SI", "ST": "SL"}
PITCH_NAMES = {
    "FF": "포심", "FT": "투심", "SI": "싱커", "FC": "커터", "SL": "슬라이더",
    "ST": "스위퍼", "CH": "체인지업", "CU": "커브", "FS": "포크",
}
PITCH_COLORS = {
    "FF": "#d62f4b", "FT": "#b9415e", "SI": "#f09a22", "FC": "#8d6d61",
    "SL": "#b5b516", "ST": "#3aa8a6", "CH": "#4bb783", "CU": "#76c8c5", "FS": "#7556b8",
}
TEAM_NAMES = {
    "OB": "두산 베어스", "SS": "삼성 라이온즈", "WO": "키움 히어로즈", "LT": "롯데 자이언츠", "HH": "한화 이글스",
    "HT": "KIA 타이거즈", "SK": "SSG 랜더스", "LG": "LG 트윈스", "NC": "NC 다이노스", "KT": "KT 위즈",
}
KOREAN_TO_CODE = {name: code for code, name in PITCH_NAMES.items()}
# A pitch type thrown at most MINOR_MAX_PITCHES times or under MINOR_USAGE_PCT of a pitcher's
# pitches is shown inside the nearest main pitch type of the same pitcher when its median
# velocity, corrected HB and IVB each fall within MERGE_TOLERANCE of that type's medians and its
# median location within LOCATION_TOLERANCE_FT. Fixed tolerances, not the main type's own
# spread: a broad main type (a slider thrown both ways) must not absorb a distinct pitch. This
# is a display grouping only: curated pitch_type and every model input keep the original label.
PROFILE_SCHEMA_VERSION = 3
PITCH_ARSENAL_SEASONS = (2022, 2023, 2024, 2025, 2026)
MINOR_MAX_PITCHES = 10
MINOR_USAGE_PCT = 5.0
MERGE_TOLERANCE = {"velocity": 5.0, "hb": 8.0, "ivb": 8.0}   # km/h, cm, cm
LOCATION_TOLERANCE_FT = 1.5
PITCH_TYPE_OVERRIDES = {
    # Confirmed by video review: 2026-07-08 SSG at Doosan, top 5th, Lee Ji-young PA, pitch 1.
    "20260708SKOB0-20260708SKOB0-037-01": "FC",
}


def _number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _season(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _stadium(value) -> str:
    name = str(value or "").replace(" ", "")
    aliases = (
        ("고척", "고척"), ("광주", "광주"), ("대구", "대구"),
        ("대전", "대전"), ("한밭", "대전"), ("문학", "문학"), ("인천", "문학"),
        ("사직", "사직"), ("수원", "수원"), ("잠실", "잠실"), ("창원", "창원"),
    )
    return next((canonical for token, canonical in aliases if token in name), name)


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


def _load_park_factors(root: Path, season: int) -> dict[tuple[str, str], tuple[float, float]]:
    """Return {(stadium, pitch code): (HB offset cm, IVB offset cm)}.

    The 2022-25 workbooks use a fixed seven-column pitch order.  Some supplied
    header cells contain duplicate labels, so positions are used deliberately;
    the intact 2023 and 2025 files establish the shared order.
    """
    source = root / "data" / "park_adjustments" / f"{season}_VB_Park_Adjustment_v1.0.xlsx"
    if not source.exists():
        raise FileNotFoundError(f"Park adjustment workbook is missing: {source}")
    workbook = load_workbook(source, read_only=True, data_only=True)
    factors: dict[tuple[str, str], list[float | None]] = {}
    try:
        if season >= 2026:
            sheet = workbook.active
            iterator = sheet.iter_rows(values_only=True)
            headers = [str(value or "") for value in next(iterator)]
            for values in iterator:
                row = dict(zip(headers, values))
                code = str(row.get("Pitch") or "").strip()
                hb, ivb = _number(row.get("HB_Offset")), _number(row.get("IVB_Offset"))
                if code in PARK_FACTOR_CODES and hb is not None and ivb is not None:
                    factors[(_stadium(row.get("Stadium")), code)] = [hb, ivb]
        else:
            for metric, index in (("IVB", 1), ("HB", 0)):
                sheet = next(sheet for sheet in workbook.worksheets if metric in sheet.title.upper())
                for values in sheet.iter_rows(min_row=2, values_only=True):
                    stadium = _stadium(values[0])
                    for column, code in enumerate(PARK_FACTOR_CODES, 1):
                        value = _number(values[column] if column < len(values) else None)
                        if value is not None:
                            factors.setdefault((stadium, code), [None, None])[index] = value
    finally:
        workbook.close()
    return {key: (float(value[0]), float(value[1])) for key, value in factors.items() if None not in value}


def _pitch_code(row: dict) -> str:
    override = PITCH_TYPE_OVERRIDES.get(str(row.get("pitch_id") or "").strip())
    if override:
        return override
    code = str(row.get("pitch_type_code") or "").strip().upper()
    if code in PITCH_CODES:
        return code
    return KOREAN_TO_CODE.get(str(row.get("pitch_type_kr") or "").strip(), "")


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


def _load_batter_hands(root: Path, season: int) -> dict[str, str]:
    """Load handedness from the canonical player dimension."""
    source = root / "data" / "curated" / "players" / "player_bio.parquet"
    if not source.exists():
        return {}
    import pyarrow.parquet as pq
    return {str(row["player_id"]): str(row.get("bats") or "") for row in pq.read_table(source, columns=["player_id", "bats"]).to_pylist()}


def _resolved_batter_stance(row: dict, batter_hands: dict[str, str]) -> str:
    stance = str(row.get("batter_stance") or "").strip().upper()
    if stance in {"L", "R"}:
        return stance
    bats = batter_hands.get(str(row.get("batter_id") or "").strip(), "")
    if bats in {"L", "R"}:
        return bats
    if bats == "S":
        release_x = _number(row.get("release_x_50"))
        if release_x is not None and abs(release_x) >= 0.1:
            return "L" if release_x < 0 else "R"
    return ""


def _throws(release_x: list[float]) -> str:
    if not release_x:
        return ""
    return "R" if median(release_x) < 0 else "L"


def build_pitch_arsenal(root: Path, season: int) -> tuple[int, int]:
    """Export searchable pitcher profiles and compact chart-ready distributions."""
    batter_hands = _load_batter_hands(root, season)
    rows = []
    for row in load_rows(root, "pitches", season):
        if _season(row.get("season")) != season or str(row.get("parse_status") or "") != "ok":
            continue
        code = _pitch_code(row)
        pitcher_name = str(row.get("pitcher_name") or "").strip()
        if code and pitcher_name:
            rows.append((row, code, str(row.get("pitcher_id") or pitcher_name).strip(), pitcher_name))
    movement = calibrate([item[0] for item in rows], [item[1] for item in rows])
    samples: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for (row, code, pitcher_id, _), (hb, ivb) in zip(rows, movement):
        samples[pitcher_id][code].append({"velocity": _number(row.get("velocity_kmh")), "hb": hb, "ivb": ivb,
                                          "px": _number(row.get("px")), "pz": _number(row.get("pz"))})
    merges, unmerged = _minor_merges(samples)
    pitchers: dict[str, dict] = {}
    eligible = 0
    for (row, original_code, pitcher_id, pitcher_name), (adjusted_hb, adjusted_ivb) in zip(rows, movement):
            code = merges.get((pitcher_id, original_code), original_code)
            pitcher = pitchers.setdefault(pitcher_id, {
                "id": pitcher_id, "name": pitcher_name, "release_x": [], "hand_release_x": [],
                "release_z": [], "velocity": [], "pitches": 0,
                "teams": [],
                "side_totals": {"L": 0, "R": 0},
                "location_n": 0, "in_zone": 0, "out_zone": 0,
                "chase_swings": 0, "swstr": 0,
                "groups": defaultdict(lambda: {
                    "n": 0, "velocity": [], "hb": [], "ivb": [], "raw_hb": [], "raw_ivb": [],
                    "release_x": [], "release_z": [], "side_counts": {"L": 0, "R": 0},
                    "location_n": 0, "in_zone": 0, "out_zone": 0,
                    "chase_swings": 0, "swstr": 0,
                    "movement_total": 0, "movement_adjusted": 0, "movement_points": [],
                    "merged_from": defaultdict(int),
                }),
            })
            team = _pitcher_team(row)
            if team and team not in pitcher["teams"]:
                pitcher["teams"].append(team)
            group = pitcher["groups"][code]
            if code != original_code:
                group["merged_from"][original_code] += 1
            pitcher["pitches"] += 1
            group["n"] += 1
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

            stance = _resolved_batter_stance(row, batter_hands)
            if stance in {"L", "R"}:
                pitcher["side_totals"][stance] += 1
                group["side_counts"][stance] += 1

            px, pz = _number(row.get("px")), _number(row.get("pz"))
            sz_top, sz_bottom = _number(row.get("sz_top")), _number(row.get("sz_bottom"))
            swing = row.get("is_swing") is True or str(row.get("is_swing") or "").lower() in {"1", "true"}
            contact = row.get("is_contact") is True or str(row.get("is_contact") or "").lower() in {"1", "true"}
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

            raw_hb = _number(row.get("horizontal_movement_cm"))
            raw_ivb = _number(row.get("vertical_movement_cm"))
            if raw_hb is not None and raw_ivb is not None:
                group["movement_total"] += 1
                if adjusted_hb is not None and adjusted_ivb is not None:
                    group["raw_hb"].append(raw_hb / CM_PER_INCH)
                    group["raw_ivb"].append(raw_ivb / CM_PER_INCH)
                    group["hb"].append(adjusted_hb / CM_PER_INCH)
                    group["ivb"].append(adjusted_ivb / CM_PER_INCH)
                    group["movement_points"].append((
                        raw_hb / CM_PER_INCH, raw_ivb / CM_PER_INCH,
                        adjusted_hb / CM_PER_INCH, adjusted_ivb / CM_PER_INCH,
                    ))
                    group["movement_adjusted"] += 1
            eligible += 1

    profiles = []
    for pitcher_id, pitcher in sorted(pitchers.items(), key=lambda item: item[1]["name"]):
        pitch_types = []
        for code, group in sorted(pitcher["groups"].items(), key=lambda item: item[1]["n"], reverse=True):
            movement_total = group["movement_total"]
            movement_adjusted = group["movement_adjusted"]
            pitch_types.append({
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
                "minor": (pitcher_id, code) in unmerged,
            })
        throws = _throws(pitcher["hand_release_x"] or pitcher["release_x"])
        payload = {
            "schema_version": PROFILE_SCHEMA_VERSION,
            "season": season,
            "source": {
                "dataset": f"data/curated/pitches/season={season}",
                "movement_calibration": "src/visualbaseball/movement_calibration.py (TrackMan-validated, analysis/movement_calibration)",
            },
            "method": {
                "movement": "corrected HB and IVB; measured minus plate-location term minus stadium-day effect from a pitcher x pitch type + stadium x day fit",
                "minor_pitch_types": (f"types with at most {MINOR_MAX_PITCHES} pitches or under {MINOR_USAGE_PCT:g}% usage are shown inside the "
                                      f"nearest main type of the same pitcher when median velocity is within {MERGE_TOLERANCE['velocity']:g} km/h, "
                                      f"corrected HB and IVB each within {MERGE_TOLERANCE['hb']:g} cm and median location within "
                                      f"{LOCATION_TOLERANCE_FT:g} ft (display only; merged_from keeps the original labels); otherwise they stay "
                                      "separate with minor=true"),
                "interval": "central 75% (12.5th to 87.5th percentile)",
                "units": {"velocity": "km/h", "movement": "in"},
                "release": "hRel/vRel are the normalized y=50 ft release_x_50/release_z_50 values",
                "zone": "abs(px) <= 10/12 ft and sz_bottom <= pz <= sz_top",
                "rates": {
                    "zone_pct": "in-zone pitches / pitches with valid ABS location",
                    "chase_pct": "swings outside the ABS zone / pitches outside the ABS zone",
                    "swstr_pct": "swings without contact / all pitches",
                },
                "percentiles": f"same pitch type, pitcher-pitch groups with at least {MIN_PERCENTILE_PITCHES} pitches",
                "percentile_scope": f"velocity_kmh is graded for every group; the rate metrics only for groups with at least {MIN_PERCENTILE_PITCHES} pitches",
            },
            "player": {
                "id": pitcher_id, "name": pitcher["name"], "throws": throws,
                "team": " · ".join(pitcher["teams"]),
                "pitches": pitcher["pitches"], "batter_side_pitches": pitcher["side_totals"],
            },
            "overall": {
                "n": pitcher["pitches"],
                "velocity_kmh": _summary(pitcher["velocity"]),
                "release": {
                    "v_rel_ft": _summary(pitcher["release_z"], 2),
                    "h_rel_ft": _summary([abs(value) for value in pitcher["release_x"]], 2),
                },
                "rates": _rates(pitcher),
                "percentiles": {"velocity_kmh": None, "zone_pct": None, "chase_pct": None, "swstr_pct": None},
                "percentile_qualified": pitcher["pitches"] >= MIN_PERCENTILE_PITCHES,
            },
            "pitch_types": pitch_types,
        }
        profiles.append(payload)

    metrics = ("zone_pct", "chase_pct", "swstr_pct")
    pitch_populations = defaultdict(lambda: defaultdict(list))
    overall_populations = defaultdict(list)
    for profile in profiles:
        for pitch in profile["pitch_types"]:
            if pitch["percentile_qualified"]:
                velocity = pitch["velocity_kmh"]["average"] if pitch["velocity_kmh"] else None
                if velocity is not None:
                    pitch_populations[pitch["code"]]["velocity_kmh"].append(velocity)
                for metric in metrics:
                    value = pitch["rates"][metric]
                    if value is not None:
                        pitch_populations[pitch["code"]][metric].append(value)
        if profile["overall"]["percentile_qualified"]:
            velocity = profile["overall"]["velocity_kmh"]["average"] if profile["overall"]["velocity_kmh"] else None
            if velocity is not None:
                overall_populations["velocity_kmh"].append(velocity)
            for metric in metrics:
                value = profile["overall"]["rates"][metric]
                if value is not None:
                    overall_populations[metric].append(value)
    # Velocity is graded for every group, including those under MIN_PERCENTILE_PITCHES: a mean
    # speed is stable at a handful of pitches in a way the rate metrics are not, so withholding it
    # only hid a reliable number.  The population itself still comes from qualified groups only,
    # and `percentile_qualified` stays false so the view keeps flagging the short sample.
    for profile in profiles:
        for pitch in profile["pitch_types"]:
            pitch["percentiles"]["velocity_kmh"] = (
                _percentile(pitch["velocity_kmh"]["average"], pitch_populations[pitch["code"]]["velocity_kmh"])
                if pitch["velocity_kmh"] else None
            )
            if pitch["percentile_qualified"]:
                pitch["percentiles"].update(
                    {metric: _percentile(pitch["rates"][metric], pitch_populations[pitch["code"]][metric]) for metric in metrics}
                )
        overall = profile["overall"]
        overall["percentiles"]["velocity_kmh"] = (
            _percentile(overall["velocity_kmh"]["average"], overall_populations["velocity_kmh"])
            if overall["velocity_kmh"] else None
        )
        if overall["percentile_qualified"]:
            overall["percentiles"].update(
                {metric: _percentile(overall["rates"][metric], overall_populations[metric]) for metric in metrics}
            )

    output = root / "web" / "data" / "pitch_arsenal" / str(season) / "players"
    output.mkdir(parents=True, exist_ok=True)
    shards = defaultdict(dict)
    player_index = []
    for payload in profiles:
        pitcher_id = payload["player"]["id"]
        throws = payload["player"]["throws"]
        shard = pitcher_id[0] if pitcher_id and pitcher_id[0].isdigit() else "other"
        shards[shard][pitcher_id] = payload
        player_index.append({
            "id": pitcher_id, "name": payload["player"]["name"], "throws": throws,
            "team": payload["player"]["team"],
            "pitches": payload["player"]["pitches"], "file": f"players/{shard}.json",
        })

    current_files = set()
    for shard, profiles in shards.items():
        filename = f"{shard}.json"
        current_files.add(filename)
        (output / filename).write_text(json.dumps({
            "season": season, "players": profiles,
        }, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    for stale in output.glob("*.json"):
        if stale.name not in current_files:
            stale.unlink()

    season_index = output.parent / "index.json"
    season_index.write_text(json.dumps({
        "season": season, "players": player_index,
    }, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")

    catalog_path = root / "web" / "data" / "pitch_arsenal" / "index.json"
    catalog = {"seasons": []}
    if catalog_path.exists():
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["seasons"] = sorted({*catalog.get("seasons", []), season}, reverse=True)
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return eligible, len(pitchers)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--season", type=int, required=True)
    args = parser.parse_args()
    rows, players = build_pitch_arsenal(Path(args.root).resolve(), args.season)
    print(f"exported {rows} pitches for {players} pitcher arsenal profiles")
