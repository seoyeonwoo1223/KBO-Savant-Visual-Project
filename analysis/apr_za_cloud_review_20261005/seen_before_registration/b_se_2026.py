"""B1·B2 등록 전에 이미 본 2026 APR B 수치를 재현합니다 (협업 창구 0005·0007).

2026-10-03 교차검증에서 계산했지만 스크립트를 커밋하지 않았던 값을 같은 정의로 다시 냅니다.
새 후보를 판정하지 않으며 공개 출력물(web/data)을 읽지 않습니다. 입력은
data/metrics/zone_awareness/2026/pitches.parquet와 같은 폴더 report.json(검산용)뿐입니다.

정의 (타자 i, 투구 t, 경기 g, e = S − p_swing, m_i = 타자 평균 e)
- B 입력: jdv_i = 100·mean_t[2(e_t − m_i)ΔV_t] = 200·Cov_n(e, ΔV)
- 현행 SE (운영 profile_summary): 100·sqrt(Σ_g U_g²)/n, U_g = Σ_t∈g [2(e_t − m_i)ΔV_t − θ_i/100]
- 공동 추정 IF SE: 같은 식에서 투구 항을 2(e_t − m_i)(ΔV_t − ΔV̄_i)로 바꾼 것 (m_i·ΔV̄_i 추정 반영)
- 두 SE 모두 G/(G−1) 보정 없음(운영 관례). 보정한 값도 함께 기록합니다.
- 비율 = 현행 SE / 공동 추정 IF SE. 1보다 크면 현행이 더 크다.
- k·APR: 운영 _plus_index에 6자리 반올림 입력을 넣어 계산합니다. 현행 SE의 k가 report.json과 같아야 합니다.

실행 (저장소 루트): PYTHONPATH=src python analysis/apr_za_cloud_review_20261005/seen_before_registration/b_se_2026.py
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.optimize import brentq
from scipy.special import expit, logit
from scipy.stats import spearmanr

from visualbaseball.zone_decision import _plus_index, r6

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PITCHES = ROOT / "data/metrics/zone_awareness/2026/pitches.parquet"
REPORT = ROOT / "data/metrics/zone_awareness/2026/report.json"


def cluster_se(values: np.ndarray, games: np.ndarray) -> tuple[float, float]:
    centred = values - values.mean()
    totals = pd.Series(centred).groupby(games).sum().to_numpy()
    raw = float(100 * np.sqrt(np.dot(totals, totals)) / len(values))
    g = len(totals)
    return raw, (raw * np.sqrt(g / (g - 1)) if g > 1 else float("nan"))


def main() -> None:
    df = pq.ParquetFile(PITCHES).read(columns=["batter_id", "game_id", "swing", "p_swing", "delta_v", "dv"]).to_pandas()
    df["batter_id"] = df.batter_id.astype(str)
    report = json.loads(REPORT.read_text())
    players, null_rows = [], []
    for batter, g in df.groupby("batter_id", sort=False):
        e = (g.swing - g.p_swing).to_numpy(); d = g.delta_v.to_numpy(); games = g.game_id.to_numpy()
        jdv = 2 * (e - e.mean()) * d
        se_cur, se_cur_g = cluster_se(jdv, games)
        se_if, se_if_g = cluster_se(2 * (e - e.mean()) * (d - d.mean()), games)
        n = len(g)
        players.append({"batter_id": batter, "pitches_seen": n, "qualified_300": n >= 300, "jdv_per_100": r6(100 * jdv.mean()),
                        "se_current": r6(se_cur), "se_if": r6(se_if), "se_current_g": se_cur_g, "se_if_g": se_if_g, "SA": 100 * e.mean()})
        if n >= 300:  # 로짓 성향 귀무: 위치 능력 없이 logit(p) + a로만 더 휘두르는 타자의 기대 B 입력
            p = g.p_swing.clip(1e-6, 1 - 1e-6).to_numpy(); lp = logit(p)
            a = brentq(lambda a: (expit(lp + a) - p).mean() - e.mean(), -8, 8)
            es = expit(lp + a) - p
            null_rows.append({"batter_id": batter, "B_null": 200 * np.mean((es - es.mean()) * d)})
    league_dv = 100 * float(df.dv.mean())
    league_jdv = sum(p["jdv_per_100"] * p["pitches_seen"] for p in players) / len(df)
    out = {"input": {"path": str(PITCHES.relative_to(ROOT)), "sha256": hashlib.sha256(PITCHES.read_bytes()).hexdigest(),
                     "pitches": int(len(df)), "model_version": report["model_version"]}}
    results = {}
    for name, key in (("current", "se_current"), ("joint_if", "se_if")):
        ps = copy.deepcopy(players)
        for p in ps:
            p["jdv_se"] = p[key]
        k = _plus_index(ps, "jdv_per_100", "jdv_se", league_dv, league_jdv, "apr", "apr_percentile")
        results[name] = {"k": k, "apr": {p["batter_id"]: p["apr"] for p in ps}}
    out["k_report_check"] = {"report_k": report["apr"]["shrinkage_k_pitches"], "current_k": results["current"]["k"],
                             "abs_diff": abs(report["apr"]["shrinkage_k_pitches"] - results["current"]["k"])}
    assert out["k_report_check"]["abs_diff"] < 1e-3
    t = pd.DataFrame(players).set_index("batter_id"); q = t[t.qualified_300]
    ratio = q.se_current / q.se_if
    a_cur = pd.Series(results["current"]["apr"]).loc[q.index]; a_if = pd.Series(results["joint_if"]["apr"]).loc[q.index]
    out["se_ratio_current_over_joint_if"] = {
        "qualified": int(len(q)), "median": float(ratio.median()),
        "quantiles_10_25_75_90": [float(x) for x in ratio.quantile([.1, .25, .75, .9])],
        "mean_se2_ratio": float((q.se_current ** 2).mean() / (q.se_if ** 2).mean()),
        "median_with_G_correction": float((q.se_current_g / q.se_if_g).median())}
    out["shrinkage"] = {"k_current": results["current"]["k"], "k_joint_if": results["joint_if"]["k"],
                        "qualified_apr_sd_current": float(a_cur.std(ddof=1)), "qualified_apr_sd_joint_if": float(a_if.std(ddof=1)),
                        "qualified_spearman": float(spearmanr(a_cur, a_if)[0]), "qualified_max_abs_diff": float((a_cur - a_if).abs().max())}
    nl = pd.DataFrame(null_rows).set_index("batter_id").join(q[["SA", "jdv_per_100"]])
    out["logit_null_B"] = {"null_vs_SA_pearson": float(np.corrcoef(nl.B_null, nl.SA)[0, 1]),
                           "null_sd_per100": float(nl.B_null.std(ddof=1)), "observed_sd_per100": float(nl.jdv_per_100.std(ddof=1)),
                           "observed_vs_SA_pearson": float(np.corrcoef(nl.jdv_per_100, nl.SA)[0, 1]),
                           "observed_minus_null_vs_SA_pearson": float(np.corrcoef(nl.jdv_per_100 - nl.B_null, nl.SA)[0, 1]),
                           "null_range_apr_points_unshrunk": [float(100 * nl.B_null.min() / league_dv), float(100 * nl.B_null.max() / league_dv)]}
    (HERE / "b_se_2026.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
