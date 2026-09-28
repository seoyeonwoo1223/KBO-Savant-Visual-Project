"""Read-only, one-command first-team SBJ source/matching audit.

    python scripts/audit_sbj_data.py --out ../audit/sbj

Every VB pitch gets one quality/matching row. A missing TrackMan pair is explicit,
never imputed from counts or ABS calls. No scoring or curated data is changed.
Each season also reports whether curated is in step with the reviewed call-correction
table (scripts/check_call_corrections.py); the audit fails if any season is not.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_call_corrections import check_season  # noqa: E402
SEASONS = tuple(range(2019, 2027))
TRACKMAN_SEASONS = tuple(range(2019, 2025))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def lf_sha256(path: Path) -> str:
    """Hash checked-out CSV independent of Git's Windows CRLF conversion."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def curated_pitches_sha256(season: int) -> str:
    directory = ROOT / "data/curated/pitches" / f"season={season}"
    files = sorted(directory.rglob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no curated pitch shards for {season}")
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(directory).as_posix().encode())
        digest.update(bytes.fromhex(sha256(path)))
    return digest.hexdigest()


def combine(quality: pd.DataFrame, coverage: pd.DataFrame | None) -> pd.DataFrame:
    if quality.pitch_id.isna().any() or quality.pitch_id.duplicated().any():
        raise ValueError("record quality must have one row per VB pitch")
    if coverage is None:
        result = quality.copy()
        result["match_status"] = "trackman_unavailable"
        result["unmatched_reason"] = "trackman_not_provided_for_season"
        return result
    if coverage.pitch_id.isna().any() or coverage.pitch_id.duplicated().any():
        raise ValueError("strict coverage must have one row per VB pitch")
    if set(quality.pitch_id) != set(coverage.pitch_id):
        raise ValueError("record quality and strict coverage pitch sets differ")
    result = quality.merge(coverage.drop(columns=quality.columns.intersection(coverage.columns).drop("pitch_id")),
                           on="pitch_id", validate="one_to_one", sort=False)
    if len(result) != len(quality) or result.match_status.isna().any():
        raise ValueError("pitch coverage was lost during the join")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="audit-only directory, outside public data paths")
    parser.add_argument("--seasons", nargs="+", type=int, default=SEASONS)
    parser.add_argument("--from-existing", action="store_true", help="recombine existing audit outputs without rerunning source checks")
    args = parser.parse_args()
    seasons = sorted(set(args.seasons))
    if not set(seasons).issubset(SEASONS):
        parser.error("seasons must be in 2019–2026")
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    if not args.from_existing:
        source = [sys.executable, str(ROOT / "analysis/trajectory_audit/pa_flow_audit.py"),
                  "--out", str(out), "--seasons", *map(str, seasons), "--skip-trackman"]
        subprocess.run(source, cwd=ROOT, env=env, check=True)
    tracked = [s for s in seasons if s in TRACKMAN_SEASONS]
    crosswalk_path = ROOT / "data/tracking/player_id_crosswalk.json"
    crosswalk = json.loads(crosswalk_path.read_text(encoding="utf-8")) if tracked else None
    if tracked and not args.from_existing:
        strict = [sys.executable, str(ROOT / "analysis/trajectory_audit/pa_flow_strict.py"),
                  "--out", str(out), "--seasons", *map(str, tracked)]
        subprocess.run(strict, cwd=ROOT, env=env, check=True)
    code = ("scripts/audit_sbj_data.py", "scripts/build_trackman_id_crosswalk.py",
            "analysis/trajectory_audit/pa_flow_audit.py", "analysis/trajectory_audit/pa_flow_strict.py",
            "scripts/check_call_corrections.py", "data/corrections/vb_bunt_foul_corrections.json")
    summary = {"scope": "VB first-team games; TrackMan both teams must be KBO first-team clubs",
               "quality_rule": "read-only flags; no event relabeling, deletion, or SBJ score change. "
                               "Call corrections enter curated only from data/corrections/vb_bunt_foul_corrections.json",
               "code_sha256": {name: sha256(ROOT / name) for name in code},
               "seasons": {}}
    for season in seasons:
        quality = pd.read_csv(out / f"record_quality_{season}.csv.gz", dtype={"pitch_id": str})
        coverage = (pd.read_csv(out / f"strict_coverage_{season}.csv.gz", dtype={"pitch_id": str})
                    if season in tracked else None)
        combined = combine(quality, coverage)
        combined.to_csv(out / f"sbj_pitch_quality_{season}.csv.gz", index=False,
                        compression={"method": "gzip", "mtime": 0})
        entry = {"vb_pitches": int(len(combined)), "curated_pitches_sha256": curated_pitches_sha256(season),
                 "review_levels": {str(k): int(v) for k, v in combined.review_level.value_counts().items()},
                 "match_status": {str(k): int(v) for k, v in combined.match_status.value_counts().items()},
                 "unmatched_reasons": {str(k): int(v) for k, v in combined.unmatched_reason.dropna().value_counts().items()}}
        if season in tracked:
            entry["match_kinds"] = {str(k): int(v) for k, v in combined.run_kind.dropna().value_counts().items()}
            path = ROOT / "data/tracking/raw" / f"season={season}" / "trackman_history.csv"
            entry["trackman_sha256"] = lf_sha256(path)
            if entry["trackman_sha256"] != crosswalk["seasons"][str(season)]["trackman_sha256"]:
                raise ValueError(f"TrackMan input changed after crosswalk build: {season}")
        entry["call_corrections"] = check_season(ROOT, season)
        summary["seasons"][str(season)] = entry
        print(season, json.dumps(entry, ensure_ascii=False), flush=True)
    summary["crosswalk_sha256"] = sha256(crosswalk_path) if tracked else None
    (out / "sbj_data_audit_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    dirty = [s for s, e in summary["seasons"].items() if not e["call_corrections"]["clean"]]
    if dirty:
        raise SystemExit(f"curated is not in step with the call-correction table: {dirty} "
                         "(run scripts/apply_call_corrections.py, then scripts/check_call_corrections.py)")


if __name__ == "__main__":
    main()
