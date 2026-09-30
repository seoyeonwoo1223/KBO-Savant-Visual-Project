"""VB 무브먼트 구장·기간·탄착 위치 보정: TrackMan 대조 검증 (연구용, 저장소 데이터는 바꾸지 않음).

TrackMan을 기준으로 한 '목표값'은 VB 척도의 TrackMan 무브먼트다.

    target_i = a_hand + b_hand * TM_i   (시즌별, 짝지어진 투구에서 추정)

    VB_i = target_i + k · loc_i + delta(park, day) + noise

- `k`는 탄착 위치 계수다. 가로 x = px(ft), 세로 z = pz − 존 중앙(ft)이다.
- 보정 후보는 TrackMan 없이 VB 투구만으로 delta를 추정한다. 2025·2026처럼 TrackMan이 없는 시즌에도
  같은 방식이 돌아야 하기 때문이다. 비교 대상은 다음과 같다.
  - 무보정
  - 기존 보정표
  - 투수×구종 + 구장×기간 이원 고정효과 (기간 = 시즌, 월, 반월, 주, 시리즈, 날짜)
  - 위 고정효과에 위치 보정·강건화·수축을 더한 변형
- 위치 계수 k는 평가 시즌을 뺀 나머지 TrackMan 시즌에서 추정한다(leave-one-season-out).

    PYTHONPATH=src python analysis/movement_calibration/calibrate.py --matched /tmp/mc --out /tmp/mc/eval
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from visualbaseball import plate_decision_v1 as old
from visualbaseball.curated import load_rows

ROOT = Path(__file__).resolve().parents[2]
COMPONENTS = {"hb": ("horizontal_movement_cm", "tm_hb"), "ivb": ("vertical_movement_cm", "induced_vert_break")}
LOC = ("x", "z")
TM_SEASONS = (2019, 2020, 2021, 2022, 2023, 2024)


def add_location(frame: pd.DataFrame) -> pd.DataFrame:
    center = (frame["sz_top"].astype(float) + frame["sz_bottom"].astype(float)) / 2
    center = center.fillna(center.median())
    frame["x"] = frame["px"].astype(float)
    frame["z"] = frame["pz"].astype(float) - center
    return frame


def add_windows(frame: pd.DataFrame) -> pd.DataFrame:
    date = pd.to_datetime(frame["game_id"].str[:8], format="%Y%m%d")
    frame["w_season"] = "all"
    frame["w_month"] = date.dt.strftime("%m")
    frame["w_half"] = date.dt.strftime("%m") + np.where(date.dt.day <= 15, "a", "b")
    frame["w_week"] = date.dt.isocalendar().week.astype(str)
    frame["w_day"] = frame["game_id"].str[:8]
    # 시리즈: 같은 구장에서 끊기지 않고 이어진 경기 날짜 묶음
    days = frame[["stadium", "w_day"]].drop_duplicates().sort_values(["stadium", "w_day"])
    gap = pd.to_datetime(days["w_day"]).groupby(days["stadium"]).diff().dt.days
    days["w_series"] = (gap.isna() | (gap > 1)).groupby(days["stadium"]).cumsum().astype(str)
    return frame.merge(days, on=["stadium", "w_day"], how="left")


def vb_frame(season: int) -> pd.DataFrame:
    columns = ["pitch_id", "game_id", "stadium", "pitcher_id", "pitch_type", "pitch_type_code", "pitch_type_kr",
               "horizontal_movement_cm", "vertical_movement_cm", "px", "pz", "sz_top", "sz_bottom", "release_x_50"]
    rows = load_rows(ROOT, "pitches", season, columns=columns)
    info = old._movement_adjust(rows, ROOT, season) if season >= 2022 else None
    frame = pd.DataFrame(rows).dropna(subset=["horizontal_movement_cm", "vertical_movement_cm", "px", "pz"])
    frame = frame[frame["pitch_type"].fillna("") != ""]
    bio = {r["player_id"]: r["throws"] for r in pq.read_table(ROOT / "data/curated/players/player_bio.parquet", columns=["player_id", "throws"]).to_pylist()}
    frame["hand"] = frame["pitcher_id"].map(bio).fillna("")
    frame["pt"] = frame["pitcher_id"] + "|" + frame["pitch_type"]
    return add_windows(add_location(frame)), info


def reference_fit(matched: pd.DataFrame, component: str) -> dict:
    """VB = a_hand + b_hand*TM + k·loc + delta(park-day): 구장-날짜 안에서 추정."""
    vb, tm = COMPONENTS[component]
    m = matched.dropna(subset=[vb, tm, "x", "z"]).copy()
    m["pd"] = m["stadium"] + "|" + m["game_id"].str[:8]
    design = pd.DataFrame({"tmR": m[tm] * (m.hand == "R"), "tmL": m[tm] * (m.hand == "L"), "L": (m.hand == "L").astype(float),
                           "x": m["x"], "z": m["z"]})
    y = m[vb].astype(float)
    dy, dx = y - y.groupby(m["pd"]).transform("mean"), design - design.groupby(m["pd"]).transform("mean")
    coef = np.linalg.lstsq(dx.to_numpy(float), dy.to_numpy(float), rcond=None)[0]
    b = dict(zip(design.columns, coef))
    # 절편(손별)은 구장-날짜 편향의 투구 가중 평균이 0이 되도록 둔다.
    resid = y - design.to_numpy(float) @ coef
    a = float(resid.mean())
    return {"bR": b["tmR"], "bL": b["tmL"], "aL": b["L"] + a, "aR": a, "kx": b["x"], "kz": b["z"]}


def target(matched: pd.DataFrame, ref: dict, component: str) -> pd.Series:
    _, tm = COMPONENTS[component]
    left = matched["hand"] == "L"
    return np.where(left, ref["aL"] + ref["bL"] * matched[tm], ref["aR"] + ref["bR"] * matched[tm])


def two_way(frame: pd.DataFrame, value: np.ndarray, window: str, robust: bool, shrink: float) -> pd.Series:
    """value = theta(투수×구종) + delta(구장×기간). delta를 투구마다 돌려준다(투구 가중 평균 0)."""
    key = frame["stadium"] + "|" + frame[window]
    y = pd.Series(value, index=frame.index)
    keep = pd.Series(True, index=frame.index)
    for _ in range(2 if robust else 1):
        yy, kk, pp = y[keep], key[keep], frame["pt"][keep]
        delta = pd.Series(0.0, index=yy.index)
        for _ in range(30):
            theta = (yy - delta).groupby(pp).transform("mean")
            delta = (yy - theta).groupby(kk).transform("mean")
        if robust:
            # 처음 적합의 잔차가 4 robust SD를 넘는 투구(실투·추적 실패 등)를 빼고 한 번 더 적합
            full = y - frame["pt"].map(theta.groupby(pp).first()) - key.map(delta.groupby(kk).first())
            scale = 1.4826 * (full - full.median()).abs().median()
            keep = (full.abs() <= 4 * scale).fillna(False)
    per_key = delta.groupby(kk).first()
    if shrink:
        # 짧은 기간은 같은 구장 시즌 효과 쪽으로 수축: n/(n+shrink)
        season_key = frame["stadium"]
        park = (yy - theta).groupby(season_key[keep]).mean()
        n = kk.value_counts()
        parks = pd.Series([k.split("|")[0] for k in per_key.index], index=per_key.index)
        w = n.reindex(per_key.index) / (n.reindex(per_key.index) + shrink)
        per_key = parks.map(park) + w * (per_key - parks.map(park))
    out = key.map(per_key).fillna(0.0)
    return out - out.mean()


CANDIDATES = {
    # 이름: (기간, 위치 보정, 강건화, 수축 n0)
    "fe_season": ("w_season", False, False, 0),
    "fe_month": ("w_month", False, False, 0),
    "fe_half": ("w_half", False, False, 0),
    "fe_week": ("w_week", False, False, 0),
    "fe_series": ("w_series", False, False, 0),
    "fe_day": ("w_day", False, False, 0),
    "fe_season_loc": ("w_season", True, False, 0),
    "fe_series_loc": ("w_series", True, False, 0),
    "fe_series_loc_robust": ("w_series", True, True, 0),
    "fe_series_loc_robust_shrink": ("w_series", True, True, 300),
    "fe_day_loc_robust_shrink": ("w_day", True, True, 300),
    "fe_week_loc_robust": ("w_week", True, True, 0),
}


def location_coefficients(refs: dict, season: int, component: str) -> tuple[float, float]:
    others = [refs[s][component] for s in refs if s != season]
    return float(np.mean([r["kx"] for r in others])), float(np.mean([r["kz"] for r in others]))


def summarize(errors: pd.Series, frame: pd.DataFrame) -> dict:
    e = errors - errors.mean()                    # 전체 수준(상수)은 보정 대상이 아님
    def cell_rms(keys, minimum):
        g = e.groupby(keys).agg(["mean", "size"]); g = g[g["size"] >= minimum]
        return float(np.sqrt(np.average(g["mean"] ** 2, weights=g["size"])))
    pitcher = e.groupby(frame["pt"]).agg(["mean", "size"]); pitcher = pitcher[pitcher["size"] >= 30]
    return {"pitch_mad": float((e - e.median()).abs().median()), "pitch_sd": float(e.std()),
            "park_day_bias_rms": cell_rms(frame["stadium"] + "|" + frame["game_id"].str[:8], 50),
            "park_type_bias_rms": cell_rms(frame["stadium"] + "|" + frame["pitch_type"], 300),
            "pitcher_type_mean_rms": float(np.sqrt(np.average(pitcher["mean"] ** 2, weights=pitcher["size"]))),
            "pitcher_type_mean_p95": float(pitcher["mean"].abs().quantile(.95)), "pitcher_types": int(len(pitcher))}


def evaluate(matched_dir: Path, out: Path, seasons=TM_SEASONS):
    matched, refs = {}, {}
    for s in seasons:
        m = pd.read_parquet(matched_dir / f"matched_{s}.parquet")
        m["tm_hb"] = -m["horz_break"]                 # TrackMan 부호를 VB 포수 시점으로
        m["hand"] = m["pitcher_hand"].str[0]
        m = m[m["hand"].isin(["R", "L"])]
        m = add_location(m.dropna(subset=["horizontal_movement_cm", "vertical_movement_cm", "horz_break", "induced_vert_break", "px", "pz"]))
        m = m[m["pitch_type"].fillna("") != ""]
        m["pt"] = m["pitcher_id"] + "|" + m["pitch_type"]
        matched[s] = m
        refs[s] = {c: reference_fit(m, c) for c in COMPONENTS}
    result = {"reference": refs, "seasons": {}}
    for s in seasons:
        vb, info = vb_frame(s)
        m = matched[s].merge(vb[["pitch_id", "w_season", "w_month", "w_half", "w_week", "w_series", "w_day"]], on="pitch_id")
        idx = vb.set_index("pitch_id").index
        pos = pd.Series(np.arange(len(vb)), index=idx).reindex(m["pitch_id"]).to_numpy()
        season_out = {"matched_pitches": int(len(m)), "vb_pitches": int(len(vb)), "location_coefficients": {}, "candidates": {}}
        for comp, (col, _) in COMPONENTS.items():
            kx, kz = location_coefficients(refs, s, comp)
            season_out["location_coefficients"][comp] = {"kx": kx, "kz": kz}
            truth = pd.Series(target(m, refs[s][comp], comp), index=m.index)
            loc_vb = kx * vb["x"].to_numpy() + kz * vb["z"].to_numpy()
            loc_m = kx * m["x"].to_numpy() + kz * m["z"].to_numpy()
            est = {"raw": np.zeros(len(m)), "raw_loc": loc_m}
            if info is not None:
                adjusted = vb["adjusted_hb_cm" if comp == "hb" else "adjusted_ivb_cm"].to_numpy()
                est["workbook"] = (vb[col].to_numpy() - adjusted)[pos]      # VB에서 빼는 양으로 통일
            for name, (window, use_loc, robust, n0) in CANDIDATES.items():
                value = vb[col].to_numpy(float) - (loc_vb if use_loc else 0)
                delta = two_way(vb, value, window, robust, n0).to_numpy()
                est[name] = delta[pos] + (loc_m if use_loc else 0)
            season_out["candidates"][comp] = {}
            for name, correction in est.items():
                errors = pd.Series(m[col].to_numpy(float) - np.nan_to_num(correction) - truth.to_numpy(), index=m.index)
                if name == "workbook":
                    errors = errors[~np.isnan(correction)]
                season_out["candidates"][comp][name] = summarize(errors, m.loc[errors.index])
            print(s, comp, {k: round(v["pitcher_type_mean_rms"], 2) for k, v in season_out["candidates"][comp].items()}, flush=True)
        result["seasons"][s] = season_out
    out.mkdir(parents=True, exist_ok=True)
    (out / "evaluation.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


FINAL = "fe_day_loc_robust_shrink"


def pooled_location_coefficients(evaluation: dict) -> dict:
    """TrackMan 시즌 전체의 위치 계수 평균. TrackMan이 없는 시즌에 그대로 쓴다."""
    refs = evaluation["reference"]
    return {c: {k: float(np.mean([refs[s][c][k] for s in refs])) for k in ("kx", "kz")} for c in COMPONENTS}


def calibrated_movement(season: int, coefficients: dict) -> pd.DataFrame:
    """VB 투구만으로 구장×날짜 편향과 탄착 위치 성분을 뺀 HB·IVB (VB 척도, 연구 후보)."""
    vb, _ = vb_frame(season)
    window, _, robust, n0 = CANDIDATES[FINAL]
    out = pd.DataFrame({"pitch_id": vb["pitch_id"].to_numpy()})
    for comp, (col, _) in COMPONENTS.items():
        loc = coefficients[comp]["kx"] * vb["x"].to_numpy() + coefficients[comp]["kz"] * vb["z"].to_numpy()
        value = vb[col].to_numpy(float) - loc
        delta = two_way(vb, value, window, robust, n0).to_numpy()
        out[f"cal_{comp}_cm"] = value - delta
        out[f"park_day_{comp}_cm"] = delta
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--matched", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--seasons", nargs="+", type=int, default=list(TM_SEASONS))
    parser.add_argument("--apply", nargs="*", type=int, default=[],
                        help="평가 결과의 위치 계수로 보정값을 만들 시즌 (예: 2024 2025 2026)")
    args = parser.parse_args()
    out = Path(args.out)
    evaluation = (json.loads((out / "evaluation.json").read_text(encoding="utf-8")) if args.apply and (out / "evaluation.json").exists()
                  else evaluate(Path(args.matched), out, tuple(args.seasons)))
    coefficients = pooled_location_coefficients(evaluation)
    (out / "location_coefficients.json").write_text(json.dumps(coefficients, indent=1), encoding="utf-8")
    for season in args.apply:
        calibrated_movement(season, coefficients).to_parquet(out / f"calibrated_{season}.parquet", index=False)
        print("calibrated", season, flush=True)
