"""기존 2026 ZA 점수의 존 높이·경계 방향 상관만 감사한다. 새 모형은 적합하지 않는다."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "results"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def correlation(a, b):
    frame = pd.DataFrame({"a": a, "b": b}).dropna()
    return {"타자수": len(frame), "Pearson": float(frame.a.corr(frame.b)),
            "Spearman": float(frame.a.corr(frame.b, method="spearman"))}


def main():
    assert sys.version_info[:2] == (3, 12)
    assert os.environ.get("OMP_NUM_THREADS") == "2"
    assert os.environ.get("OPENBLAS_NUM_THREADS") == "2"
    assert os.environ.get("PYTHONPATH") == "src"
    versions = {name: importlib.metadata.version(name) for name in
                ("numpy", "pandas", "pyarrow", "scikit-learn", "scipy", "openpyxl")}
    for line in (ROOT / "constraints-za.txt").read_text().splitlines():
        if "==" in line:
            name, version = line.split("==")
            assert versions[name] == version
    # 인벤토리와 계약을 먼저 읽는다. curated 원문이나 인덱스는 필요 없다.
    json.loads((ROOT / "data/curated/summary.json").read_text())
    json.loads((ROOT / "data/curated/schema.json").read_text())
    source = ROOT / "data/metrics/zone_awareness/2026/pitches.parquet"
    columns = ["batter_id", "sz_top", "sz_bottom", "judgment", "swing", "p_swing",
               "p_zone", "x_relative", "z_relative", "strikes_before", "region"]
    pitches = pq.ParquetFile(source).read(columns=columns).to_pandas()
    pitches["batter_id"] = pitches.batter_id.astype(str)
    pitches["height_cm"] = (pitches.sz_top - pitches.sz_bottom) * 30.48
    pitches["residual"] = pitches.swing - pitches.p_swing
    pitches["margin"] = 2 * pitches.p_zone - 1
    grouped = pitches.groupby("batter_id", sort=True)
    by_batter = grouped.agg(n=("judgment", "size"), height_cm=("height_cm", "mean"),
                             za_raw=("judgment", "mean"), residual=("residual", "mean"),
                             mean_p_zone=("p_zone", "mean"))
    by_batter.za_raw *= 100
    public_path = ROOT / "web/data/zone_awareness/2026/leaderboard.json"
    public = json.loads(public_path.read_text())
    public_frame = pd.DataFrame(public["players"]).assign(
        batter_id=lambda frame: frame.batter_id.astype(str)).set_index("batter_id")
    by_batter = by_batter.join(public_frame[["za_plus", "apr", "swing_aggression"]])
    qualified = by_batter.loc[by_batter.n >= 300].copy()
    assert len(qualified) == public["qualified_batters"]
    error = float((qualified.za_raw - public_frame.loc[qualified.index, "za_raw"]).abs().max())
    assert error < 0.0001
    result = {"상태": "확인함(코드·데이터로 확인함)", "대상": "2026 기존 za7.7 산출물",
              "입력열": columns, "버전": versions, "읽은투구수": len(pitches),
              "자격타자수": len(qualified), "ZA_raw_최대오차": error,
              "존높이_cm_분위수": {str(p): float(qualified.height_cm.quantile(p))
                                for p in (.1, .5, .9)},
              "전체상관": {name: correlation(qualified.height_cm, qualified[name])
                          for name in ("za_raw", "za_plus", "apr", "swing_aggression", "mean_p_zone")}}
    # max 거리가 Shadow 범위인 공을 지배 축으로 배정한다. 모서리도 중복 집계하지 않는다.
    x, z = pitches.x_relative.abs(), pitches.z_relative.abs()
    shadow = np.maximum(x, z).between(2 / 3, 4 / 3, inclusive="right")
    masks = {"좌우": shadow & (x > z), "상하": shadow & (z >= x)}
    result["경계방향정의"] = "2/3 < max(|x|,|z|) ≤ 4/3; |x|>|z|는 좌우, 나머지는 상하"
    edge_results = {}
    for label, mask in masks.items():
        edge = pitches.loc[mask].groupby("batter_id").agg(
            edge_n=("judgment", "size"), za_edge=("judgment", "mean"),
            r_edge=("residual", "mean"), q_edge=("p_zone", "mean"))
        edge = qualified[["height_cm", "n"]].join(edge)
        # 작은 경계 표본의 잡음을 줄이기 위한 기술 집계 제한. 채택 게이트가 아니다.
        edge = edge.loc[edge.edge_n >= 30].copy()
        edge.za_edge *= 100
        edge.r_edge *= 100
        edge_results[label] = {"최소경계투구수": 30,
                              "평균경계투구수": float(edge.edge_n.mean()),
                              "높이와_경계ZA_상관": correlation(edge.height_cm, edge.za_edge),
                              "높이와_스윙잔차_상관": correlation(edge.height_cm, edge.r_edge),
                              "높이와_p_zone_상관": correlation(edge.height_cm, edge.q_edge)}
        for name in ("edge_n", "za_edge", "r_edge", "q_edge"):
            qualified[f"{label}_{name}"] = edge[name]
    result["경계방향별"] = edge_results
    result["한계"] = ["존 높이는 sz_top−sz_bottom 평균이며 선수 실제 신장을 측정한 값이 아니다.",
                     "2026만 투구 근거가 있으므로 +0.08~+0.30이라는 8시즌 범위는 재현하지 않았다.",
                     "좌우에서도 상관이 생기는 것이 체격 편향이 없다는 증거는 아니다. p_zone 상하 cm 간격은 좌우 공에도 적용된다.",
                     "선수 유형·투구 구성과 누락된 체격 특성의 효과는 이 상관으로 분리할 수 없다. 원인 판정은 추정이다.",
                     "체격 특성을 넣는 신규 재적합·후보 점수·성능 실험은 실행하지 않았다."]
    paths = [source, public_path, Path(__file__).resolve(), ROOT / "constraints-za.txt",
             ROOT / "data/curated/summary.json", ROOT / "data/curated/schema.json",
             ROOT / "src/visualbaseball/zone_decision.py", ROOT / "src/visualbaseball/plate_decision_v1.py"]
    result["입력_SHA256"] = {str(path.relative_to(ROOT)): digest(path) for path in paths}
    result["기준커밋"] = "d7bb6fa1"
    OUT.mkdir(exist_ok=True)
    (OUT / "height_audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    qualified.sort_index().to_csv(OUT / "height_audit_2026.csv", float_format="%.8f", na_rep="", lineterminator="\n")
    print(json.dumps({"전체상관": result["전체상관"], "경계방향별": edge_results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
