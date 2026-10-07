"""ZA 존 정규화 설계 전 입력 감사 (협업 창구 0009). 모형을 적합하지 않습니다.

1. data/curated/players/player_bio.parquet의 신장·체중이 채워져 있는지
2. 시즌별 VB sz_top/sz_bottom이 타자별 상수인지, 신장 비례(타자 간 sz_top/sz_bottom 비가 상수)인지
3. 같은 타자의 ABS 시즌 존이 시즌 사이, 그리고 구심 시즌 존과 어떻게 이어지는지
4. 구심 시즌 투구 중 그 타자가 2024–2026에 ABS 존을 가진 비율 (신장 역산 가능 범위, 전체 투구 기준 근사)

대상은 시즌별 300구 이상 타자(전체 투구 기준)다. 판단 적격 필터는 적용하지 않는다.
실행 (저장소 루트): PYTHONPATH=src python analysis/apr_za_cloud_review_20261005/seen_before_registration/sz_height_audit.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from visualbaseball.curated import load_rows

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
CM = 30.48


def season_table(year: int) -> pd.DataFrame:
    df = pd.DataFrame(load_rows(ROOT, "pitches", year, columns=["batter_id", "sz_top", "sz_bottom"])).dropna()
    df["batter_id"] = df.batter_id.astype(str)
    return df


def main() -> None:
    bio = pq.ParquetFile(ROOT / "data/curated/players/player_bio.parquet").read().to_pandas()
    out = {"player_bio": {"rows": int(len(bio)), "non_null": {c: int(bio[c].notna().sum()) for c in ("height_cm", "weight_kg", "birth_date")},
                          "source_name": sorted(bio.source_name.dropna().unique().tolist())}}
    medians, pitches_by_batter, seasons = {}, {}, {}
    for year in range(2019, 2027):
        df = season_table(year)
        g = df.groupby("batter_id"); n = g.size(); big = n[n >= 300].index
        med = g[["sz_top", "sz_bottom"]].median()
        ratio = (med.sz_top / med.sz_bottom).loc[big]
        seasons[str(year)] = {
            "batters_300": int(len(big)),
            "single_sz_top_share": float((g.sz_top.nunique().loc[big] == 1).mean()),
            "median_within_batter_sd_top_cm": float(g.sz_top.std().loc[big].median() * CM),
            "median_top_cm": float(med.sz_top.loc[big].median() * CM),
            "top_over_bottom_median": float(ratio.median()),
            "top_over_bottom_iqr": float(ratio.quantile(.75) - ratio.quantile(.25)),
            "top_over_bottom_p05_p95": [float(ratio.quantile(.05)), float(ratio.quantile(.95))]}
        medians[year], pitches_by_batter[year] = med, n
    out["seasons"] = seasons

    def carry(a: int, b: int) -> dict:
        both = medians[a].index.intersection(medians[b].index)
        both = both[(pitches_by_batter[a].loc[both] >= 300) & (pitches_by_batter[b].loc[both] >= 300)]
        r = medians[b].loc[both].sz_top / medians[a].loc[both].sz_top
        return {"n": int(len(both)), "top_ratio_median": float(r.median()), "top_ratio_iqr": float(r.quantile(.75) - r.quantile(.25)),
                "top_pearson": float(np.corrcoef(medians[a].loc[both].sz_top, medians[b].loc[both].sz_top)[0, 1])}

    out["same_batter"] = {"2024_to_2025": carry(2024, 2025), "2025_to_2026": carry(2025, 2026), "2023_to_2024": carry(2023, 2024)}
    abs_batters = set().union(*(set(medians[y].index) for y in (2024, 2025, 2026)))
    out["umpire_pitch_share_with_abs_zone"] = {
        str(y): float(pitches_by_batter[y][pitches_by_batter[y].index.isin(abs_batters)].sum() / pitches_by_batter[y].sum())
        for y in range(2019, 2024)}
    (HERE / "sz_height_audit.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
