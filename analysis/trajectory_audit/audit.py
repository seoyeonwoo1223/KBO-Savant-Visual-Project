"""VB 무브먼트·궤적 이상값 전수조사와 ABS p_zone(pStrike) 영향 평가 (연구용, 데이터는 바꾸지 않음).

    PYTHONPATH=src OMP_NUM_THREADS=2 python analysis/trajectory_audit/audit.py --out /tmp/audit

단계
1. scope   시즌별 원본 JSON·curated 투구 수와 출처. 2022–2024는 curated가 Excel 변환본이라
           나중에 추가된 원본 JSON 스냅샷과 투구 단위로 대조한다.
2. pitches 모든 투구의 궤적 자기 일관성, 가속도, 투수×구종 안 극단값, 릴리스 일관성을 계산하고 분류한다.
3. impact  2024–2026 ABS p_zone을 운영 모델 그대로 적합해, 의심 투구의 판정면을 신뢰 가능한 대체
           좌표로 바꿨을 때 p_zone·ABS 테이크 판정 일치·선수 SBJ가 얼마나 바뀌는지 잰다.

분류 (한 투구에 하나, 위에서부터 우선)
- `no_trajectory`   궤적 계산 불가(trajectory_status != valid). 운영 p_zone은 이미 px/pz로 대체한다.
- `trajectory_inconsistent`  궤적이 VB가 보고한 탄착 위치를 1cm 넘게 벗어나거나, 제공 무브먼트가
                    궤적 가속도(50ft→앞면)와 1cm 넘게 다르다. 판정면을 궤적으로 계산하면 안 되는 투구.
- `implausible_acceleration`  회전 가속도 sqrt(ax²+(az+g)²) > 45 ft/s² 또는 ay가 5–55 ft/s² 밖.
                    2019–2023 전 시즌 최댓값(약 37 ft/s²)을 크게 넘는 값으로, 측정 오류 의심.
- `extreme_release_mismatch`  투수×구종 안 보정 무브먼트가 극단(robust z > 5)이고, 궤적으로 역산한
                    55ft 릴리스 위치도 그 투수의 평소 위치에서 극단(robust z > 5, 15cm 초과)이다.
                    투수는 릴리스를 일정하게 반복하므로 가속도 오류가 역산 릴리스로 번진 것으로 의심.
- `extreme_consistent`  무브먼트는 극단이지만 궤적이 탄착과 맞고 릴리스도 평소와 같다. 실제 특이 구질·
                    실투일 수 있으며 측정 오류로 판정하지 않는다.
극단 판정의 척도는 그 투수·구종의 robust SD(MAD×1.4826, 하한 2cm)라 변동이 큰 투수는 넓게 본다.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from visualbaseball import plate_decision_v1 as old
from visualbaseball import zone_decision as zd
from visualbaseball.curated import CM_PER_FOOT, load_rows
from visualbaseball.movement_calibration import calibrate
from visualbaseball.pitch_arsenal import _pitch_code

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "zone_decision"))
import pswing_input_ablation as ablation  # noqa: E402  (운영 p_swing과 오차 0으로 같은 적합)

G = 32.174
SEASONS = tuple(range(2019, 2027))
ABS_SEASONS = (2024, 2025, 2026)
PLANES = {"front": 17 / 12, "mid": 8.5 / 12, "back": 0.0}
MAGNUS_LIMIT = 45.0
AY_RANGE = (5.0, 55.0)
EXTREME_Z = 5.0
RELEASE_CM = 15.0
LOCATION_TOL_CM = 1.0
BOUNDARY_CM = 5.0
ABS_SIDE_CM = 27.1          # ABS 좌우 경계: 중간면 ±27.1cm
COLUMNS = ["pitch_id", "game_id", "stadium", "pitcher_id", "pitcher_name", "pitch_type_code", "pitch_type_kr",
           "trajectory_status", "horizontal_movement_cm", "vertical_movement_cm", "velocity_kmh", "px", "pz",
           "sz_top", "sz_bottom", "x0", "y0", "z0", "vx0", "vy0", "vz0", "ax", "ay", "az",
           "release_x_55", "release_z_55", "pitch_call_code"]


# ---------------------------------------------------------------- 1. scope
def _raw_pitch_count(path: Path) -> int:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return sum(len(pa.get("pitches") or []) for half in payload.get("pbpData", []) for pa in half.get("pas") or [])


def scope(out: Path) -> dict:
    from visualbaseball.build_curated import prepare_game
    from visualbaseball.curated import normalize_trajectory
    summary = json.loads((ROOT / "data/curated/summary.json").read_text(encoding="utf-8"))["seasons"]
    result = {}
    for season in SEASONS:
        raw = sorted((ROOT / "data/raw" / str(season)).glob("*.json"))
        manifests = [json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "data/curated/sources" / f"season={season}").glob("*.json")]
        entry = {"curated_pitches": summary[str(season)]["tables"]["pitches"]["rows"], "curated_games": len(manifests),
                 "raw_json_games": len(raw), "raw_json_pitches": sum(_raw_pitch_count(p) for p in raw),
                 "curated_from_raw_json_games": sum(m.get("raw_sha256") is not None for m in manifests)}
        if entry["curated_from_raw_json_games"] == 0 and raw:
            # Excel 변환본 curated를 나중에 추가된 원본 JSON과 투구 단위로 대조한다.
            fields = ("px", "pz", "horizontal_movement_cm", "vertical_movement_cm", "velocity_kmh", "sz_top", "sz_bottom",
                      "x0", "y0", "z0", "vx0", "vy0", "vz0", "ax", "ay", "az")
            curated = pd.DataFrame(load_rows(ROOT, "pitches", season, columns=["pitch_id", *fields])).set_index("pitch_id")
            matched = missing = 0
            differing = Counter()
            for path in raw:
                prepared = prepare_game(json.loads(path.read_text(encoding="utf-8-sig")), season=season, naver_enrichment=None)
                for row in prepared.pitches:
                    row = normalize_trajectory(row)
                    if row["pitch_id"] not in curated.index:
                        missing += 1
                        continue
                    matched += 1
                    stored = curated.loc[row["pitch_id"]]
                    for field in fields:
                        a, b = old._safe_float(row.get(field)), old._safe_float(stored[field])
                        if not (np.isnan(a) and np.isnan(b)) and not abs(a - b) <= 1e-6:
                            differing[field] += 1
            entry["raw_vs_curated"] = {"raw_pitches_matched_by_pitch_id": matched, "raw_pitches_not_in_curated": missing,
                                       "curated_pitches_not_in_raw": int(len(curated) - matched),
                                       "pitches_with_field_difference": dict(differing)}
        result[season] = entry
        print("scope", season, json.dumps(entry, ensure_ascii=False), flush=True)
    (out / "scope.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


# ---------------------------------------------------------------- 2. pitches
def _time(d: pd.DataFrame, target_y: float) -> pd.Series:
    # curated._time_to_plane과 같은 근(절댓값이 작은 쪽)
    a, b, c = d.ay, d.vy0, d.y0 - target_y
    disc = b * b - 2 * a * c
    r1, r2 = (-b + np.sqrt(disc)) / a, (-b - np.sqrt(disc)) / a
    return pd.Series(np.where(np.abs(r1) < np.abs(r2), r1, r2), index=d.index)


def _position(d: pd.DataFrame, t: pd.Series) -> tuple[pd.Series, pd.Series]:
    return (d.x0 + d.vx0 * t + .5 * d.ax * t * t) * CM_PER_FOOT, (d.z0 + d.vz0 * t + .5 * d.az * t * t) * CM_PER_FOOT


def _robust_z(values: pd.Series, groups: pd.Series, floor: float, minimum: int = 20) -> pd.Series:
    centre = values.groupby(groups).transform("median")
    spread = (values - centre).abs().groupby(groups).transform("median") * 1.4826
    count = values.groupby(groups).transform("count")
    z = (values - centre) / spread.clip(lower=floor)
    return z.where(count >= minimum)


def pitch_frame(season: int) -> pd.DataFrame:
    rows = load_rows(ROOT, "pitches", season, columns=COLUMNS)
    d = pd.DataFrame(rows)
    d["code"] = [_pitch_code(r) for r in rows]
    for c in COLUMNS[7:-1]:
        if c != "trajectory_status":
            d[c] = pd.to_numeric(d[c], errors="coerce")
    valid = d.trajectory_status.eq("valid")
    t = {name: _time(d, y) for name, y in PLANES.items()}
    t50 = _time(d, 50.0)
    for name in PLANES:
        d[f"x_{name}_cm"], d[f"z_{name}_cm"] = _position(d, t[name])
    # VB px 기준면: 2023까지 앞면, 2024부터 중간면(ABS 좌우 판정면). pz는 모든 시즌 앞면.
    x_plane = "mid" if season >= 2024 else "front"
    d["px_plane"] = x_plane
    d["loc_err_x_cm"] = d[f"x_{x_plane}_cm"] - d.px * CM_PER_FOOT
    d["loc_err_z_cm"] = d["z_front_cm"] - d.pz * CM_PER_FOOT
    window = t["front"] - t50              # VB 제공 무브먼트는 50ft→앞면 구간(2026-07-16 이후 y0=55여도 동일)
    d["mov_resid_hb_cm"] = d.horizontal_movement_cm - .5 * d.ax * window ** 2 * CM_PER_FOOT
    d["mov_resid_ivb_cm"] = d.vertical_movement_cm - .5 * (d.az + G) * window ** 2 * CM_PER_FOOT
    d["magnus"] = np.sqrt(d.ax ** 2 + (d.az + G) ** 2)
    for c in [c for c in d if c.endswith("_cm") or c == "magnus"]:
        d.loc[~valid, c] = np.nan
    cal = calibrate(rows, list(d.code))
    d["cal_hb_cm"] = [c[0] for c in cal]
    d["cal_ivb_cm"] = [c[1] for c in cal]
    group = d.pitcher_id.astype(str) + "|" + d.code
    d["z_hb"] = _robust_z(d.cal_hb_cm, group, 2.0)
    d["z_ivb"] = _robust_z(d.cal_ivb_cm, group, 2.0)
    d["z_velocity"] = _robust_z(d.velocity_kmh, group, 1.0)
    pitcher = d.pitcher_id.astype(str)
    for axis in ("x", "z"):
        values = d[f"release_{axis}_55"]
        centre = values.groupby(pitcher).transform("median")
        d[f"release_{axis}_dev_cm"] = values - centre
        d[f"z_release_{axis}"] = _robust_z(values, pitcher, 2.0)
    zmid = (d.sz_top + d.sz_bottom) / 2
    zhalf = (d.sz_top - d.sz_bottom) / 2
    d["zone_distance"] = np.maximum((d.px / (10 / 12)).abs(), ((d.pz - zmid) / zhalf).abs())
    extreme = (d.z_hb.abs() > EXTREME_Z) | (d.z_ivb.abs() > EXTREME_Z)
    release_bad = ((d.z_release_x.abs() > EXTREME_Z) & (d.release_x_dev_cm.abs() > RELEASE_CM)) | \
                  ((d.z_release_z.abs() > EXTREME_Z) & (d.release_z_dev_cm.abs() > RELEASE_CM))
    inconsistent = (d.loc_err_x_cm.abs() > LOCATION_TOL_CM) | (d.loc_err_z_cm.abs() > LOCATION_TOL_CM) | \
                   (d.mov_resid_hb_cm.abs() > LOCATION_TOL_CM) | (d.mov_resid_ivb_cm.abs() > LOCATION_TOL_CM)
    implausible = (d.magnus > MAGNUS_LIMIT) | (d.ay < AY_RANGE[0]) | (d.ay > AY_RANGE[1])
    d["category"] = np.select(
        [~valid, valid & inconsistent, valid & implausible, valid & extreme & release_bad, valid & extreme],
        ["no_trajectory", "trajectory_inconsistent", "implausible_acceleration", "extreme_release_mismatch", "extreme_consistent"],
        "normal")
    d["season"] = season
    return d


# ---------------------------------------------------------------- 3. impact
def anchored_planes(d: pd.DataFrame) -> pd.DataFrame:
    """보고된 탄착(px·pz)에 고정하고, 그 투수·구종의 중앙 접근각으로 중간면·끝면을 다시 계산한다.
    2024+ px는 이미 중간면이므로 x는 px 그대로다. 17인치 구간의 가속도 효과(0.1cm 미만)는 무시한다."""
    slope = (d.z_mid_cm - d.z_front_cm) / (8.5 / 12 * CM_PER_FOOT)          # 앞면→중간면 1ft당 z 변화
    back_slope = (d.z_back_cm - d.z_front_cm) / (17 / 12 * CM_PER_FOOT)
    group = d.pitcher_id.astype(str) + "|" + d.code
    med = slope.groupby(group).transform("median").fillna(slope.median())
    med_back = back_slope.groupby(group).transform("median").fillna(back_slope.median())
    z_front = d.pz * CM_PER_FOOT
    heights = pd.concat([z_front + med * (8.5 / 12 * CM_PER_FOOT), z_front + med_back * (17 / 12 * CM_PER_FOOT)], axis=1)
    return pd.DataFrame({"x_mid_relative": d.px / zd.PLATE_HALF_WIDTH_FT,
                         "top_gap_cm": heights.max(axis=1) - d.sz_top * CM_PER_FOOT,
                         "bottom_gap_cm": heights.min(axis=1) - d.sz_bottom * CM_PER_FOOT}, index=d.index)


def impact(season: int, frame: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    rows, _ = ablation.load(ROOT, season)                         # 운영 zone_decision.load_rows 그대로(+pitch_id)
    info = frame.set_index("pitch_id")
    ids = [r["pitch_id"] for r in rows]
    sub = info.loc[ids]
    alt = anchored_planes(sub.reset_index()).set_index(pd.Index(ids))
    dates = np.array(sorted({r["game_id"][:8] for r in rows}))
    index = {pid: i for i, pid in enumerate(ids)}
    out = pd.DataFrame({"pitch_id": ids, "game_id": [r["game_id"] for r in rows], "batter_id": [str(r["batter_id"]) for r in rows],
                        "swing": [int(r["decision_type"] == "Swing") for r in rows], "event": [r["event"] for r in rows],
                        "category": sub.category.to_numpy(),
                        "x_mid_relative": [r["x_mid_relative"] for r in rows], "top_gap_cm": [r["top_gap_cm"] for r in rows],
                        "bottom_gap_cm": [r["bottom_gap_cm"] for r in rows], "plane_fallback": [bool(r.get("plane_fallback")) for r in rows]})
    for c in ("x_mid_relative", "top_gap_cm", "bottom_gap_cm"):
        out[f"alt_{c}"] = alt[c].to_numpy()
    out["p_zone"] = out["p_zone_alt"] = out["p_zone_front"] = out["p_swing"] = np.nan
    for block in np.array_split(dates, zd.CROSSFIT_FOLDS):
        held = set(block)
        train = [r for r in rows if r["game_id"][:8] not in held]
        test = [r for r in rows if r["game_id"][:8] in held]
        pos = np.array([index[r["pitch_id"]] for r in test])
        out.loc[pos, "p_zone"] = old.predict_pzone(train, test, zd.PZONE_ABS)
        replaced = [{**r, **{c: out.at[index[r["pitch_id"]], f"alt_{c}"] for c in zd.PZONE_ABS}} for r in test]
        out.loc[pos, "p_zone_alt"] = old.predict_pzone(train, replaced, zd.PZONE_ABS)
        out.loc[pos, "p_zone_front"] = old.predict_pzone(train, test, old.PZONE_NUMERIC)
        out.loc[pos, "p_swing"] = ablation.propensity(train, test, *ablation.CANDIDATES["H1"])[0]
        print("  impact", season, "block", len(test), flush=True)
    out["called_strike"] = np.where(out.swing == 0, (out.event == "CalledStrike").astype(float), np.nan)
    side = out.x_mid_relative.abs() * zd.PLATE_HALF_WIDTH_FT * CM_PER_FOOT
    out["boundary"] = (out.top_gap_cm.abs() < BOUNDARY_CM) | (out.bottom_gap_cm.abs() < BOUNDARY_CM) | ((side - ABS_SIDE_CM).abs() < BOUNDARY_CM)
    out["plane_shift_cm"] = np.maximum.reduce([
        ((out.x_mid_relative - out.alt_x_mid_relative).abs() * zd.PLATE_HALF_WIDTH_FT * CM_PER_FOOT).to_numpy(),
        (out.top_gap_cm - out.alt_top_gap_cm).abs().to_numpy(), (out.bottom_gap_cm - out.alt_bottom_gap_cm).abs().to_numpy()])
    return summarize_impact(season, out), out


SUSPECT = ("trajectory_inconsistent", "implausible_acceleration", "extreme_release_mismatch")


def _player_change(out: pd.DataFrame, replace: pd.Series) -> dict:
    p_new = np.where(replace, out.p_zone_alt, out.p_zone)
    j0 = 100 * (out.swing - out.p_swing) * (2 * out.p_zone - 1)
    j1 = 100 * (out.swing - out.p_swing) * (2 * p_new - 1)
    g = pd.DataFrame({"b": out.batter_id, "j0": j0, "j1": j1}).groupby("b").agg(n=("j0", "size"), a=("j0", "mean"), b=("j1", "mean"))
    q = g[g.n >= 300]
    delta = (q.b - q.a)
    ranks = (q.a.rank(ascending=False) - q.b.rank(ascending=False)).abs()
    return {"pitches_replaced": int(replace.sum()), "qualified": int(len(q)), "max_abs_delta_pp": float(delta.abs().max()),
            "players_delta_over_0_01pp": int((delta.abs() > 0.01).sum()), "players_delta_over_0_05pp": int((delta.abs() > 0.05).sum()),
            "max_rank_change": int(ranks.max())}


def summarize_impact(season: int, out: pd.DataFrame) -> dict:
    result = {"pitches": int(len(out)), "plane_fallback": int(out.plane_fallback.sum()), "by_category": {}}
    for cat, g in out.groupby("category"):
        dp = (g.p_zone_alt - g.p_zone).abs()
        takes = g[g.swing == 0]
        agree = lambda p: float(((p > .5) == (takes.called_strike == 1)).mean()) if len(takes) else None
        result["by_category"][cat] = {
            "pitches": int(len(g)), "boundary": int(g.boundary.sum()),
            "plane_shift_cm_p50_p99_max": [float(x) for x in np.nanquantile(g.plane_shift_cm, [.5, .99, 1])] if g.plane_shift_cm.notna().any() else None,
            "abs_dp_zone_alt_p50_p99_max": [float(x) for x in np.nanquantile(dp, [.5, .99, 1])],
            "dp_over_0_05": int((dp > .05).sum()), "crosses_half": int(((g.p_zone > .5) != (g.p_zone_alt > .5)).sum()),
            "boundary_and_dp_over_0_05": int((g.boundary & (dp > .05)).sum()),
            "abs_dp_zone_front_p50_p99": [float(x) for x in np.nanquantile((g.p_zone_front - g.p_zone).abs(), [.5, .99])],
            "takes": int(len(takes)), "take_call_agreement": {"current": agree(takes.p_zone), "anchored": agree(takes.p_zone_alt), "front_model": agree(takes.p_zone_front)},
        }
    result["sbj_if_replaced"] = {
        "suspect_categories": _player_change(out, out.category.isin(SUSPECT)),
        "suspect_and_extreme_consistent": _player_change(out, out.category.isin(SUSPECT + ("extreme_consistent",))),
        "every_pitch_sensitivity": _player_change(out, out.category.ne("no_trajectory")),
    }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--skip-scope", action="store_true")
    args = parser.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    if not args.skip_scope:
        scope(out)
    counts, impacts = {}, {}
    for season in SEASONS:
        frame = pitch_frame(season)
        counts[season] = {"pitches": int(len(frame)), **{k: int(v) for k, v in frame.category.value_counts().items()}}
        keep = frame[frame.category.ne("normal")]
        keep.drop(columns=[c for c in keep if c.startswith(("x_", "z_front", "z_mid", "z_back"))]).to_parquet(out / f"flagged_{season}.parquet", index=False)
        print("pitches", season, counts[season], flush=True)
        if season in ABS_SEASONS:
            impacts[season], detail = impact(season, frame)
            detail.to_parquet(out / f"impact_{season}.parquet", index=False)
            print("impact", season, json.dumps(impacts[season], ensure_ascii=False)[:1500], flush=True)
    (out / "categories.json").write_text(json.dumps(counts, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "impact.json").write_text(json.dumps(impacts, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
