"""Research-only TrackMan release-slot estimates, with explicit missing inputs.

This is NOT a reproduction of Statcast's measured arm angle. No production
metric, canonical dataset, or existing player biography is overwritten.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
import unicodedata

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import requests

CLUBS = frozenset({"DOO_BEA", "HAN_EAG", "KIA_TIG", "KIW_HER", "KT_WIZ", "LG_TWI",
                  "LOT_GIA", "NC_DIN", "SAM_LIO", "SK_WYV", "SSG_LAN"})
REFERENCE_URLS = ("https://baseballsavant.mlb.com/leaderboard/pitcher-arm-angles",)
KBO_URL = "https://www.koreabaseball.com/Record/Player/PitcherDetail/Basic.aspx?playerId={}"
HEIGHT_COLUMNS = ["player_id", "player_name", "height_cm", "source_url", "source_sha256", "collected_at"]
TM_COLUMNS = ["trackman_id", "season", "game_date", "pitcher_trackman_id", "pitcher_hand",
              "pitcher_team", "batter_team", "tagged_pitch_type", "rel_height", "rel_side", "extension"]


def digest(path: Path, normalize_newlines: bool = False) -> str:
    content = path.read_bytes()
    if normalize_newlines:
        content = content.replace(b"\r\n", b"\n")
    return hashlib.sha256(content).hexdigest()


def normalized_name(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", str(value)))


class ProfileParser(HTMLParser):
    """Read named KBO profile spans; unrelated page numbers cannot be heights."""
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.active = None
        self.fields = {}

    def handle_starttag(self, tag, attrs):
        if tag in {"br", "img", "input", "meta", "link", "hr"}:
            return
        self.depth += 1
        identifier = dict(attrs).get("id", "").lower()
        for suffix, key in (("lblname", "name"), ("lblheightweight", "height_weight")):
            if identifier.endswith(suffix):
                self.active = (self.depth, key)
                self.fields[key] = ""

    def handle_endtag(self, tag):
        if self.active and self.active[0] == self.depth:
            self.active = None
        self.depth = max(0, self.depth - 1)

    def handle_data(self, data):
        if self.active:
            self.fields[self.active[1]] += data


def parse_kbo_profile(html: str, expected_name: str) -> float:
    parser = ProfileParser()
    parser.feed(html)
    name = parser.fields.get("name", "").strip()
    if not name or normalized_name(name) != normalized_name(expected_name):
        raise ValueError(f"KBO profile identity mismatch: expected {expected_name!r}, found {name!r}")
    match = re.search(r"\b(\d{3}(?:\.\d+)?)\s*cm\b", parser.fields.get("height_weight", ""), re.I)
    if not match or not 140 <= float(match[1]) <= 220:
        raise ValueError("KBO profile has no plausible labelled height in cm")
    return float(match[1])


@dataclass(frozen=True)
class Assumptions:
    # Exploratory scenario choices, NOT published anatomical constants or CIs.
    shoulder_height_ratio: float = 0.72
    shoulder_side_ratio: float = 0.10
    shoulder_height_ratio_low: float = 0.65
    shoulder_height_ratio_high: float = 0.80
    shoulder_side_shift_m: float = 0.20

    def __post_init__(self):
        if not 0 < self.shoulder_height_ratio_low <= self.shoulder_height_ratio <= self.shoulder_height_ratio_high < 1:
            raise ValueError("Shoulder height scenario ratios must be ordered and between 0 and 1")
        if not 0 <= self.shoulder_side_ratio < 1 or self.shoulder_side_shift_m < 0:
            raise ValueError("Invalid lateral shoulder scenario")


def frontal_angle(side, height, shoulder_side, shoulder_height):
    dx = np.abs(np.asarray(side, dtype=float) - shoulder_side)
    dz = np.asarray(height, dtype=float) - shoulder_height
    angle = np.degrees(np.arctan2(dz, dx))
    return np.where(np.hypot(dx, dz) > 1e-10, angle, np.nan)


def elevation_3d(side, height, extension, shoulder_side, shoulder_height, shoulder_extension):
    """Requires an independently observed shoulder's forward position."""
    dx = np.asarray(side, dtype=float) - shoulder_side
    dy = np.asarray(extension, dtype=float) - shoulder_extension
    dz = np.asarray(height, dtype=float) - shoulder_height
    return np.where(np.sqrt(dx*dx + dy*dy + dz*dz) > 1e-10,
                    np.degrees(np.arctan2(dz, np.hypot(dx, dy))), np.nan)


def score(frame: pd.DataFrame, assumptions: Assumptions = Assumptions()) -> pd.DataFrame:
    out = frame.copy()
    side, z = out.rel_side.to_numpy(float), out.rel_height.to_numpy(float)
    h = out.height_cm.to_numpy(float) / 100
    sign = out.pitcher_hand.map({"Right": 1., "Left": -1.}).to_numpy(float)
    release_ok = np.isfinite(side) & np.isfinite(z) & (np.abs(side) <= 2) & (z >= .05) & (z <= 2.7)
    height_ok = np.isfinite(h) & (h >= 1.4) & (h <= 2.2)
    personal_ok = release_ok & height_ok & np.isfinite(sign)
    ext = out.extension.to_numpy(float)
    ext_ok = np.isfinite(ext) & (ext >= .5) & (ext <= 3)
    out["release_valid"] = release_ok
    out["extension_valid"] = ext_ok
    out["hand_side_conflict"] = np.isfinite(sign) & np.isfinite(side) & (sign*side < 0)
    out["fixed_130cm_proxy_deg"] = np.where(release_ok, frontal_angle(side, z, 0., 1.3), np.nan)
    sx = sign * assumptions.shoulder_side_ratio * h
    sz = assumptions.shoulder_height_ratio * h
    out["assumed_shoulder_side_m"] = np.where(personal_ok, sx, np.nan)
    out["assumed_shoulder_height_m"] = np.where(personal_ok, sz, np.nan)
    out["estimated_frontal_deg"] = np.where(personal_ok, frontal_angle(side, z, sx, sz), np.nan)
    # Exact extrema over the stated shoulder rectangle, including its interior
    # closest lateral point. Corner-only checks miss vertical alignments.
    xmin, xmax = sx-assumptions.shoulder_side_shift_m, sx+assumptions.shoulder_side_shift_m
    nearest = np.maximum(np.maximum(xmin-side, side-xmax), 0)
    farthest = np.maximum(np.abs(side-xmin), np.abs(side-xmax))
    dzlow, dzhigh = z-assumptions.shoulder_height_ratio_high*h, z-assumptions.shoulder_height_ratio_low*h
    candidates = np.stack([np.degrees(np.arctan2(dz, distance))
                           for dz in (dzlow, dzhigh) for distance in (nearest, farthest)])
    out["scenario_low_deg"] = np.where(personal_ok, candidates.min(axis=0), np.nan)
    out["scenario_high_deg"] = np.where(personal_ok, candidates.max(axis=0), np.nan)
    out["scenario_width_deg"] = out.scenario_high_deg-out.scenario_low_deg
    out["extension_height_ratio"] = np.where(height_ok & ext_ok, ext/h, np.nan)
    out["estimate_status"] = np.select(
        [~release_ok, ~height_ok, ~np.isfinite(sign), ~np.isfinite(out.estimated_frontal_deg)],
        ["invalid_release", "missing_height", "unknown_hand", "degenerate_geometry"],
        default="assumption_based_not_validated")
    return out


def load_height_table(path: Path, bio: pd.DataFrame) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=HEIGHT_COLUMNS)
    heights = pd.read_csv(path, dtype={"player_id": str})
    if not set(HEIGHT_COLUMNS).issubset(heights.columns):
        raise ValueError(f"Height table requires {HEIGHT_COLUMNS}")
    if heights.player_id.isna().any() or heights.player_id.duplicated().any():
        raise ValueError("Height table must have one non-null row per player_id")
    heights["height_cm"] = pd.to_numeric(heights.height_cm, errors="raise")
    if not heights.height_cm.between(140, 220).all():
        raise ValueError("Height values must be verified cm values in [140, 220]")
    if not heights.source_url.fillna("").str.startswith("https://").all():
        raise ValueError("Every collected height requires an HTTPS provenance URL")
    if not heights.source_sha256.fillna("").str.fullmatch(r"[0-9a-f]{64}").all():
        raise ValueError("Every collected height requires a source SHA-256")
    if pd.to_datetime(heights.collected_at, utc=True, errors="coerce").isna().any():
        raise ValueError("Every collected height requires a valid collection timestamp")
    names = bio.set_index("player_id").player_name.to_dict()
    for row in heights.itertuples():
        if row.player_id not in names or normalized_name(row.player_name) != normalized_name(names[row.player_id]):
            raise ValueError(f"Height identity does not match biography: {row.player_id}")
    return heights


def load_season(root: Path, season: int, bio: pd.DataFrame, crosswalk: dict, overlap: dict):
    path = root / f"data/tracking/raw/season={season}/trackman_history.csv"
    source_hash = digest(path, normalize_newlines=True)
    expected = crosswalk["seasons"][str(season)]["trackman_sha256"]
    if source_hash != expected:
        raise ValueError(f"TrackMan source no longer matches player crosswalk: {season}")
    raw = pd.read_csv(path, usecols=TM_COLUMNS, dtype={"trackman_id": str, "pitcher_trackman_id": str})
    if not raw.season.eq(season).all():
        raise ValueError(f"Mixed season file: {path}")
    frame = raw[raw.pitcher_team.isin(CLUBS) & raw.batter_team.isin(CLUBS)].copy()
    if frame.trackman_id.isna().any() or frame.trackman_id.duplicated().any():
        raise ValueError(f"Nonunique TrackMan pitch key: {season}")
    pairs = crosswalk["seasons"][str(season)]["roles"]["pitcher"]["pairs"]
    mapping = {p["trackman_id"]: p["visualbaseball_id"] for p in pairs}
    if len(mapping) != len(pairs) or len(set(mapping.values())) != len(pairs):
        raise ValueError("Accepted crosswalk must be one-to-one")
    shared = set(overlap["seasons"][str(season)]["roles"]["pitcher"]["shared_ids"])
    frame["player_id"] = frame.pitcher_trackman_id.map(mapping)
    equal = frame.player_id.isna() & frame.pitcher_trackman_id.isin(shared)
    frame.loc[equal, "player_id"] = frame.loc[equal, "pitcher_trackman_id"]
    frame["identity_method"] = np.where(frame.pitcher_trackman_id.isin(mapping), "accepted_crosswalk",
                                         np.where(equal, "same_season_equality", "unresolved"))
    frame = frame.merge(bio[["player_id", "player_name"]], on="player_id", how="left", validate="many_to_one")
    for col in ("rel_side", "rel_height", "extension"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["game_date"] = pd.to_datetime(frame.game_date, format="mixed", errors="raise").dt.strftime("%Y-%m-%d")
    return frame, {"season": season, "raw_rows": len(raw), "major_rows": len(frame),
                   "excluded_non_major": len(raw)-len(frame), "source_sha256": source_hash,
                   "duplicate_pitch_keys": 0, "unresolved_identity_rows": int(frame.player_id.isna().sum()),
                   "release_missing": {c: int(frame[c].isna().sum()) for c in ("rel_side", "rel_height", "extension")}}


def collect_heights(players: pd.DataFrame, path: Path, bio: pd.DataFrame, cache: Path):
    """Resume verified heights; stop early on proxy denial instead of flooding it."""
    existing = load_height_table(path, bio)
    known = set(existing.player_id)
    rows = existing.to_dict("records")
    events = []
    cache.mkdir(parents=True, exist_ok=True)
    for player in players.sort_values("player_id").itertuples():
        if player.player_id in known or pd.isna(player.player_id) or pd.isna(player.player_name):
            continue
        if not re.fullmatch(r"\d{5}", player.player_id):
            events.append({"player_id": player.player_id, "status": "not_kbo_profile_id"})
            continue
        url = KBO_URL.format(player.player_id)
        try:
            response = requests.get(url, timeout=20)
            if response.status_code == 403:
                events.append({"player_id": player.player_id, "status": "access_denied", "url": url})
                break
            response.raise_for_status()
            raw_path = cache / f"{player.player_id}.html"
            raw_path.write_bytes(response.content)
            height = parse_kbo_profile(response.text, player.player_name)
            rows.append({"player_id": player.player_id, "player_name": player.player_name, "height_cm": height,
                         "source_url": url, "source_sha256": digest(raw_path),
                         "collected_at": datetime.now(timezone.utc).isoformat()})
            known.add(player.player_id)
            pd.DataFrame(rows, columns=HEIGHT_COLUMNS).to_csv(path, index=False)
            events.append({"player_id": player.player_id, "status": "collected"})
        except requests.exceptions.ProxyError:
            events.append({"player_id": player.player_id, "status": "proxy_blocked", "url": url})
            break
        except (requests.RequestException, ValueError) as error:
            event = {"player_id": player.player_id, "status": "unusable_profile", "error_type": type(error).__name__}
            if isinstance(error, ValueError):
                event["reason"] = str(error)
            events.append(event)
        time.sleep(.5)
    if not path.exists():
        pd.DataFrame(rows, columns=HEIGHT_COLUMNS).to_csv(path, index=False)
    return events


def reference_access(cache: Path):
    records = []
    cache.mkdir(parents=True, exist_ok=True)
    for index, url in enumerate(REFERENCE_URLS):
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            if "throwing shoulder" not in response.text or "perfectly horizontal" not in response.text:
                raise ValueError("Response does not contain the official arm-angle definition")
            path = cache / f"official_reference_{index}.html"
            path.write_bytes(response.content)
            records.append({"url": url, "status": "verified_savant_definition", "sha256": digest(path)})
        except (requests.RequestException, ValueError) as error:
            records.append({"url": url, "status": "unavailable", "error_type": type(error).__name__})
    return records


def validate_reference(frame: pd.DataFrame, labels_path: Path):
    labels = pd.read_csv(labels_path, dtype={"trackman_id": str})
    required = {"season", "trackman_id", "reference_angle_deg", "source_url", "definition"}
    if not required.issubset(labels.columns):
        raise ValueError(f"Reference observations require {sorted(required)}")
    if labels.duplicated(["season", "trackman_id"]).any() or labels[list(required)].isna().any().any():
        raise ValueError("Reference observations require complete unique pitch keys and provenance")
    if not labels.definition.eq("frontal_shoulder_to_ball").all():
        raise ValueError("Only reference angles in the same frontal definition may be compared")
    labels["reference_angle_deg"] = pd.to_numeric(labels.reference_angle_deg, errors="raise")
    if not labels.reference_angle_deg.between(-90, 90).all():
        raise ValueError("Reference frontal angles must be in [-90, 90]")
    matched = labels.merge(frame, on=["season", "trackman_id"], how="left", validate="one_to_one", indicator=True)
    if not matched._merge.eq("both").all():
        raise ValueError("Reference observations include pitch keys outside the selected population")
    if not matched.estimated_frontal_deg.notna().all():
        raise ValueError("Reference observations lack personalized estimates; collect heights first")
    matched["error_deg"] = matched.estimated_frontal_deg-matched.reference_angle_deg
    matched["within_scenario"] = matched.reference_angle_deg.between(matched.scenario_low_deg, matched.scenario_high_deg)
    def metrics(group):
        return {"n": len(group), "mae_deg": float(group.error_deg.abs().mean()),
                "bias_deg": float(group.error_deg.mean()), "scenario_coverage": float(group.within_scenario.mean())}
    report = {"status": "reference_comparison_only_no_predictive_model_fit", **metrics(matched),
              "pitchers": int(matched.player_id.nunique()), "by_hand": {}, "by_pitcher": {}}
    for column, key in (("pitcher_hand", "by_hand"), ("player_id", "by_pitcher")):
        report[key] = {str(value): metrics(group) for value, group in matched.groupby(column)}
    return report, matched.drop(columns="_merge")


def summarize(frame, keys):
    # Unresolved players retain their TrackMan ID instead of collapsing into NaN.
    def valid_extension_median(values):
        valid = values[values.between(.5, 3)].dropna()
        return valid.median() if len(valid) else np.nan

    grouped = frame.groupby(keys, dropna=False, sort=True)
    return grouped.agg(pitches=("trackman_id", "size"), valid_release_pitches=("release_valid", "sum"),
                       estimated_pitches=("estimated_frontal_deg", "count"),
                       fixed_proxy_median_deg=("fixed_130cm_proxy_deg", "median"),
                       estimated_median_deg=("estimated_frontal_deg", "median"),
                       estimated_q10_deg=("estimated_frontal_deg", lambda x: x.quantile(.1)),
                       estimated_q90_deg=("estimated_frontal_deg", lambda x: x.quantile(.9)),
                       scenario_low_median_deg=("scenario_low_deg", "median"),
                       scenario_high_median_deg=("scenario_high_deg", "median"),
                       scenario_width_median_deg=("scenario_width_deg", "median"),
                       height_cm=("height_cm", "first"),
                       extension_median_m=("extension", valid_extension_median),
                       extension_height_ratio_median=("extension_height_ratio", "median")).reset_index()


def run(root: Path, output: Path, years: list[int], height_path: Path, collect: bool = False,
        fetch_reference: bool = False, labels: Path | None = None, assumptions: Assumptions = Assumptions()):
    output.mkdir(parents=True, exist_ok=True)
    height_path.parent.mkdir(parents=True, exist_ok=True)
    bio = pq.read_table(root / "data/curated/players/player_bio.parquet").to_pandas()
    if bio.player_id.isna().any() or bio.player_id.duplicated().any():
        raise ValueError("Biography IDs must be complete and unique")
    crosswalk_path = root / "data/tracking/player_id_crosswalk.json"
    overlap_path = root / "data/tracking/player_id_overlap.json"
    crosswalk = json.loads(crosswalk_path.read_text())
    overlap = json.loads(overlap_path.read_text())
    frames, source_reports = [], []
    for year in years:
        frame, report = load_season(root, year, bio, crosswalk, overlap)
        frames.append(frame)
        source_reports.append(report)
    raw = pd.concat(frames, ignore_index=True)
    if raw.duplicated(["season", "trackman_id"]).any():
        raise ValueError("Repeated seasons would duplicate pitch keys")
    players = raw[["player_id", "player_name"]].dropna().drop_duplicates()
    events = collect_heights(players, height_path, bio, output / "source_cache/kbo") if collect else []
    heights = load_height_table(height_path, bio)
    raw = raw.merge(heights, on=["player_id", "player_name"], how="left", validate="many_to_one")
    result = score(raw, assumptions)
    result.to_parquet(output / "pitches.parquet", index=False)
    keys = ["season", "pitcher_trackman_id", "player_id", "player_name", "pitcher_hand"]
    summarize(result, keys).to_csv(output / "pitchers.csv", index=False)
    summarize(result, keys+["tagged_pitch_type"]).to_csv(output / "pitcher_pitch_types.csv", index=False)
    days = summarize(result, keys+["game_date"])
    days.to_parquet(output / "pitcher_days.parquet", index=False)
    pending = players.merge(heights[["player_id", "height_cm"]], on="player_id", how="left", validate="one_to_one")
    pending = pending[pending.height_cm.isna()].copy()
    pending["candidate_source_url"] = pending.player_id.map(KBO_URL.format)
    pending.to_csv(output / "missing_heights.csv", index=False)
    validation = {"status": "not_validated_no_reference_observations", "n": 0}
    if labels is not None:
        validation, observations = validate_reference(result, labels)
        observations.to_csv(output / "reference_comparison.csv", index=False)
    reference = reference_access(output / "source_cache/official") if fetch_reference else []
    report = {"schema_version": 1, "scope": "both teams are recognized first-team KBO clubs, 2019-2024 TrackMan",
              "target": "Savant convention: frontal throwing-shoulder-to-ball angle to horizontal; KBO shoulder position is assumed, not observed",
              "savant_definition_status": "verified_official_leaderboard_definition", "reference_sources": reference,
              "assumptions": asdict(assumptions), "units": {"rel_height": "m", "rel_side": "m", "extension": "m", "height_cm": "cm"},
              "coordinate_status": "TrackMan rel_side predominantly positive Right / negative Left; units inferred from export scale and existing matching code, vendor datum not independently verified",
              "shoulder_height_status": "free scenario parameter includes unobserved posture, not an anatomical estimate established by evidence",
              "scenario_status": "sensitivity to user-adjustable shoulder assumptions; NOT confidence intervals",
              "extension_role": "extension / height diagnostic only; frontal angle does not use extension; 3D angle requires independent shoulder forward position",
              "reference_validation": validation, "height_collection": events,
              "raw_rows": sum(r["raw_rows"] for r in source_reports), "major_pitches": len(result),
              "resolved_players": len(players), "height_players": int(len(heights[heights.player_id.isin(players.player_id)])),
              "personalized_pitches": int(result.estimated_frontal_deg.notna().sum()),
              "statuses": {str(k): int(v) for k, v in result.estimate_status.value_counts().items()},
              "invalid_extension_rows": int((~result.extension_valid).sum()),
              "hand_side_conflict_rows": int(result.hand_side_conflict.sum()),
              "bio_height_nonnull": int(bio.height_cm.notna().sum()), "sources": source_reports,
              "input_hashes": {"crosswalk": digest(crosswalk_path), "overlap": digest(overlap_path),
                               "bio": digest(root / "data/curated/players/player_bio.parquet"),
                               "heights": digest(height_path) if height_path.exists() else None,
                               "implementation": digest(Path(__file__)),
                               "reference_observations": digest(labels) if labels is not None else None},
              "limitations": ["No shoulder coordinates, body pose, arm lengths, or video truth in raw TrackMan data.",
                              "Height cannot uniquely identify arm angle; extension is not arm length.",
                              "Collected present-day height is not a season-specific historical measurement.",
                              "A player-ID match is not a pitch-to-pitch match; this study reads TrackMan directly.",
                              "No production arm-angle or movement-zones output was changed."]}
    (output / "quality_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path, default=Path(".cache/arm_angle"))
    parser.add_argument("--seasons", type=int, nargs="+", default=list(range(2019, 2025)))
    parser.add_argument("--heights", type=Path, default=Path("data/tracking/player_heights.csv"))
    parser.add_argument("--collect-heights", action="store_true")
    parser.add_argument("--fetch-reference", action="store_true")
    parser.add_argument("--reference-observations", type=Path)
    parser.add_argument("--shoulder-height-ratio", type=float, default=.72)
    parser.add_argument("--shoulder-side-ratio", type=float, default=.10)
    parser.add_argument("--shoulder-height-low", type=float, default=.65)
    parser.add_argument("--shoulder-height-high", type=float, default=.80)
    parser.add_argument("--shoulder-side-shift-m", type=float, default=.20)
    args = parser.parse_args()
    assumptions = Assumptions(args.shoulder_height_ratio, args.shoulder_side_ratio,
                              args.shoulder_height_low, args.shoulder_height_high, args.shoulder_side_shift_m)
    report = run(args.root.resolve(), args.out.resolve(), args.seasons, args.heights.resolve(),
                 args.collect_heights, args.fetch_reference, args.reference_observations, assumptions)
    print(json.dumps({k: report[k] for k in ("major_pitches", "resolved_players", "height_players",
                                           "personalized_pitches", "statuses", "reference_validation")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
