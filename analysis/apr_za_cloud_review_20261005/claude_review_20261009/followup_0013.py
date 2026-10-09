"""협업 창구 0014: 0013 요청 2·3에 대한 입력 확인. 모형을 적합하지 않으며 새 실험이 아니다.

1. 입력 고정: 0012 heights()가 읽은 data/curated/pitches는 git에 추적되는 파일이다. 시즌별 tree SHA를 기록하고
   e48da3a2와 같음을 확인한 뒤 heights()를 다시 돌려 cross_check.json과 같은지 본다.
2. sz 정합과 기본값: ABS 시즌 투구마다 상단·하단에서 각각 역산한 신장이 맞는지 보고, 맞지 않는 (sz_top, sz_bottom) 쌍이
   여러 타자에게 공유되는 값인지, 원자료(data/raw)의 szTop/szBot부터 그런지, 언제 나타나는지 기록한다.
3. 역산 신장의 해상도: 정합 쌍에서 가능한 신장 구간이 0.1cm·0.5cm·1cm·0.25in 격자를 포함하는 비율을 균등 기대와 비교한다.
4. 판정면: 운영 함수(curated._at_plane, zone_decision.judgment_plane_location)로 부호 있는 중간면−끝면 높이차를 구하고,
   2026 판단 적격 투구와 연결해 0012/0013의 1,577·848구를 부호 있는 일반식으로 다시 센다.
   2024–2026 curated의 궤적 유효·판정면 계산 가능·보고 위치 불일치 비율도 기록한다(판단 적격 필터 전 분모).

실행 (저장소 루트): PYTHONPATH=src OMP_NUM_THREADS=2 python analysis/apr_za_cloud_review_20261005/claude_review_20261009/followup_0013.py
"""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from visualbaseball.curated import _at_plane, load_table
from visualbaseball.zone_decision import PLANE_Y_FT, judgment_plane_location, reported_location_disagrees
from visualbaseball.swing_take import PLATE_HALF_WIDTH_FT

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cross_check  # noqa: E402  0012 스크립트의 heights()를 그대로 다시 쓴다

SOURCE = cross_check.SOURCE
CM = 30.48
ABS_RATIO = cross_check.ABS_RATIO
BACK_OFFSET_CM, OFFICIAL_HALF_WIDTH_CM = 1.5, 43.18 / 2 + 2
CONSISTENT_CM = .1  # sz는 .001ft로 반올림되어 있어 역산 신장의 반올림 폭은 상단 ±.027cm, 하단 ±.056cm다
TRAJ = ["trajectory_valid", "x0", "y0", "z0", "vx0", "vy0", "vz0", "ax", "ay", "az", "px", "pz"]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def provenance() -> dict:
    trees = {str(y): git("rev-parse", f"HEAD:data/curated/pitches/season={y}") for y in range(2019, 2027)}
    pinned = {str(y): git("rev-parse", f"{SOURCE}:data/curated/pitches/season={y}") for y in range(2019, 2027)}
    assert trees == pinned
    subprocess.run(["git", "diff", "--quiet", SOURCE, "--", "data/curated/pitches"], cwd=ROOT, check=True)
    subprocess.run(["git", "diff", "--quiet", "--", "data/curated/pitches"], cwd=ROOT, check=True)
    ignored = subprocess.run(["git", "check-ignore", "-q", "data/curated/pitches/season=2024/month=04.parquet"], cwd=ROOT).returncode == 0
    rerun = cross_check.heights()
    saved = json.loads((HERE / "cross_check.json").read_text())["heights"]
    return {"curated_pitches_tree_sha_by_season": trees, "equal_to_source_commit_trees": True, "working_tree_clean": True,
            "curated_pitches_gitignored": ignored, "heights_rerun_equals_cross_check_json": rerun == saved}


def abs_rows(year: int) -> pd.DataFrame:
    cols = ["pitch_id", "game_id", "game_date", "batter_id", "batter_name", "sz_top", "sz_bottom", *TRAJ]
    df = load_table(ROOT, "pitches", year, columns=cols).to_pandas()
    df["batter_id"] = df.batter_id.astype(str)
    return df


def sz_audit(frames: dict[int, pd.DataFrame]) -> dict:
    out = {}
    for year, df in frames.items():
        top, bottom = ABS_RATIO[year]
        v = df.dropna(subset=["sz_top", "sz_bottom"])
        gap = v.sz_top * CM / top - v.sz_bottom * CM / bottom
        bad = v[gap.abs() > CONSISTENT_CM]
        pairs = (bad.groupby(["sz_top", "sz_bottom"])
                 .agg(pitches=("pitch_id", "size"), batters=("batter_id", "nunique"), games=("game_id", "nunique"),
                      first=("game_date", "min"), last=("game_date", "max"))
                 .sort_values("pitches", ascending=False))
        pairs["implied_top_cm"] = [t * CM / top for t, _ in pairs.index]
        pairs["implied_bottom_cm"] = [b * CM / bottom for _, b in pairs.index]
        batters_bad = bad.groupby("batter_id").size()
        out[str(year)] = {
            "pitches": int(len(df)), "sz_missing": int(len(df) - len(v)),
            "inconsistent_pitches": int(len(bad)), "inconsistent_share": float(len(bad) / len(v)),
            "batters": int(v.batter_id.nunique()), "batters_with_inconsistent_pitches": int(len(batters_bad)),
            "inconsistent_pairs": int(len(pairs)),
            "top_pairs": [{"sz_top_ft": float(t), "sz_bottom_ft": float(b), **{k: (int(r[k]) if k in ("pitches", "batters", "games") else
                          (round(float(r[k]), 2) if k.startswith("implied") else str(r[k]))) for k in pairs.columns}}
                          for (t, b), r in pairs.head(8).iterrows()],
        }
    return out


def default_timeline(frames: dict[int, pd.DataFrame]) -> dict:
    """0013이 든 두 사례: 2026 ID56637, 2025 ID50106. 경기별 (sz_top, sz_bottom)과 원자료 값."""
    out = {}
    for year, pid in ((2026, "56637"), (2025, "50106")):
        f = frames[year][frames[year].batter_id == pid]
        games = (f.groupby(["game_date", "game_id", "sz_top", "sz_bottom"]).size().rename("pitches").reset_index()
                 .sort_values(["game_date", "game_id"]))
        raw_pairs = {}
        for gid in games.game_id.unique():
            path = ROOT / "data/raw" / str(year) / f"{gid}.json"
            if not path.exists():
                raw_pairs[gid] = None
                continue
            d = json.loads(path.read_text())
            seen = {(p.get("szTop"), p.get("szBot")) for half in d["pbpData"] for pa in half["pas"]
                    if str(pa.get("batterId")) == pid for p in pa["pitches"]}
            raw_pairs[gid] = sorted([list(x) for x in seen])
        rows = []
        for r in games.itertuples():
            raw = raw_pairs[r.game_id]
            rows.append({"game_date": str(r.game_date), "game_id": r.game_id, "sz_top_ft": float(r.sz_top), "sz_bottom_ft": float(r.sz_bottom),
                         "pitches": int(r.pitches), "raw_has_same_pair": None if raw is None else [float(r.sz_top), float(r.sz_bottom)] in raw})
        out[f"{year}_{pid}"] = {"name": str(f.batter_name.iloc[0]), "games": rows}
    return out


def resolution(frames: dict[int, pd.DataFrame]) -> dict:
    """정합 쌍(타자-시즌의 주 쌍)에서 반올림을 감안한 가능한 신장 구간이 격자점을 포함하는지."""
    grids = {"0.1cm": .1, "0.5cm": .5, "1cm": 1., "0.25in": .635, "0.5in": 1.27}
    hits, expected, n = {g: 0 for g in grids}, {g: 0. for g in grids}, 0
    for year, df in frames.items():
        top, bottom = ABS_RATIO[year]
        v = df.dropna(subset=["sz_top", "sz_bottom"])
        main = v.groupby(["batter_id", "sz_top", "sz_bottom"]).size().reset_index().sort_values(0).drop_duplicates("batter_id", keep="last")
        for t, b in zip(main.sz_top, main.sz_bottom):
            lo = max((t - .0005) * CM / top, (b - .0005) * CM / bottom)
            hi = min((t + .0005) * CM / top, (b + .0005) * CM / bottom)
            if hi < lo:
                continue
            n += 1
            for name, g in grids.items():
                hits[name] += int(np.floor(hi / g) * g >= lo)
                expected[name] += min(1., (hi - lo) / g)
    return {"batter_seasons": n, **{g: {"observed": hits[g] / n, "uniform_expected": expected[g] / n} for g in grids}}


def planes(frames: dict[int, pd.DataFrame]) -> tuple[dict, pd.DataFrame]:
    out, keep = {}, None
    for year, df in frames.items():
        rows = df.to_dict("records")
        delta, gaps, disagree, computable = [], [], [], []
        for r in rows:
            mid = back = None
            if r["trajectory_valid"]:
                mid, back = _at_plane(r, PLANE_Y_FT["mid"]), _at_plane(r, PLANE_Y_FT["back"])
            ok = mid is not None and back is not None
            computable.append(ok)
            delta.append(mid[1] - back[1] if ok else np.nan)
            disagree.append(bool(reported_location_disagrees(r)))
            gaps.append(judgment_plane_location(r) if r["px"] is not None and r["sz_top"] is not None else None)
        d = np.array(delta, float)
        c = np.array(computable)
        out[str(year)] = {
            "pitches": len(rows), "trajectory_valid_share": float(df.trajectory_valid.fillna(False).astype(bool).mean()),
            "both_planes_computable_share": float(c.mean()), "reported_location_disagrees_share": float(np.mean(disagree)),
            "signed_mid_minus_back_cm_min_p01_p50_p99": [float(np.nanmin(d)), *np.nanquantile(d, [.01, .5, .99]).tolist()],
            "signed_negative_share": float(np.nanmean(d < 0)), "signed_below_1_5cm_share": float(np.nanmean(d < BACK_OFFSET_CM)),
        }
        if year == 2026:
            g = pd.DataFrame([x if x else {} for x in gaps])
            keep = pd.DataFrame({"game_id": df.game_id.values, "batter_id": df.batter_id.values, "delta": d,
                                 "x": g.x_mid_relative.values, "top": g.top_gap_cm.values, "bottom": g.bottom_gap_cm.values})
    return out, keep


def eligible_2026(curated: pd.DataFrame) -> dict:
    blob = subprocess.check_output(["git", "show", f"{SOURCE}:{cross_check.PITCHES}"], cwd=ROOT)
    assert hashlib.sha256(blob).hexdigest() == cross_check.PITCH_SHA
    za = pq.ParquetFile(io.BytesIO(blob)).read(columns=["game_id", "batter_id", "x_mid_relative", "top_gap_cm", "bottom_gap_cm", "swing"]).to_pandas()
    za["batter_id"] = za.batter_id.astype(str)
    key = ["game_id", "batter_id", "kx", "kt", "kb"]
    for f, (x, t, b) in ((za, ("x_mid_relative", "top_gap_cm", "bottom_gap_cm")), (curated, ("x", "top", "bottom"))):
        f["kx"], f["kt"], f["kb"] = f[x].round(6), f[t].round(6), f[b].round(6)
    c = curated.dropna(subset=["kx"]).drop_duplicates(key, keep=False)
    m = za.merge(c[key + ["delta"]], on=key, how="left", validate="many_to_one")
    d = m.delta.to_numpy()
    matched = np.isfinite(d)
    # 0013 일반식: delta=z_mid−z_back(부호 있음)
    top_shift = np.maximum(0, BACK_OFFSET_CM - d) - np.maximum(0, -d)
    bottom_shift = np.minimum(0, BACK_OFFSET_CM - d) - np.minimum(0, -d)
    top, bottom = m.top_gap_cm + top_shift, m.bottom_gap_cm + bottom_shift
    old_v = (m.top_gap_cm <= 0) & (m.bottom_gap_cm >= 0)
    new_v = (top <= 0) & (bottom >= 0)
    horizontal = (m.x_mid_relative.abs() * PLATE_HALF_WIDTH_FT * CM) <= OFFICIAL_HALF_WIDTH_CM
    take = (m.swing.to_numpy() == 0) & matched
    return {"eligible": int(len(m)), "matched_to_curated_trajectory": int(matched.sum()),
            "signed_mid_minus_back_cm_min": float(np.nanmin(d)), "signed_negative": int((d[matched] < 0).sum()),
            "takes": int(take.sum()), "vertical_flip_takes": int(((old_v != new_v) & take).sum()),
            "full_center_flip_takes": int(((old_v != new_v) & horizontal & take).sum()),
            "x_relative_unit_cm": PLATE_HALF_WIDTH_FT * CM, "official_half_width_cm": OFFICIAL_HALF_WIDTH_CM}


def main() -> None:
    out = {"head": git("rev-parse", "HEAD"), "source_commit": SOURCE, "provenance": provenance()}
    frames = {y: abs_rows(y) for y in (2024, 2025, 2026)}
    out["sz_consistency"] = sz_audit(frames)
    out["default_cases"] = default_timeline(frames)
    out["height_resolution"] = resolution(frames)
    out["planes"], curated_2026 = planes(frames)
    out["eligible_2026"] = eligible_2026(curated_2026)
    out["note"] = "입력 기하·원자료 확인. 콜·p_zone·정확성·모형 적합 없음. ZN-A 등록 시 이미 본 결과로 밝힌다."
    (HERE / "followup_0013.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
