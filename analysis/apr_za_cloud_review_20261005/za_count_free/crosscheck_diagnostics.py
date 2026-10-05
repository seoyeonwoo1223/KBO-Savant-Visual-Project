"""교차검증 응답(claude-crosscheck-response.md)의 진단 수치를 재현합니다.

ZC 러너의 고정 예측(predictions)을 그대로 쓰고 새 후보를 채택 판정하지 않습니다.
- 카운트 구성 의존성: 적격 타자의 Z0_call·Z0_free·차이와 2S/0S/3B 투구 비중의 Pearson
- 점수 차이 크기: |Z0_free - Z0_call|가 Z0_call SE를 넘는 비율
- 반분 신뢰도 차이: 같은 ID에서 Spearman-Brown 차이의 선수 bootstrap 95% CI
- 로짓 성향 귀무: 위치 능력 없이 logit(p)+a_i로만 더 휘두르는 타자의 기대 점수와 SA 상관

실행 (저장소 루트):
  PYTHONPATH=src OMP_NUM_THREADS=2 PYTHONDONTWRITEBYTECODE=1 \
    python analysis/apr_za_cloud_review_20261005/za_count_free/crosscheck_diagnostics.py
캐시가 없으면 run_experiment.predictions가 2022·2023 모형을 다시 적합합니다.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.optimize import brentq
from scipy.special import expit, logit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_experiment as runner  # noqa: E402
from metrics import player_scores  # noqa: E402

SEED = 20261005
BOOT = 2000


def pearson(a, b):
    return float(np.corrcoef(np.asarray(a, float), np.asarray(b, float))[0, 1])


def shares(df):
    g = df.groupby("batter_id")
    return pd.DataFrame({"two_strike": g.strikes_before.apply(lambda s: float((s == 2).mean())),
                         "zero_strike": g.strikes_before.apply(lambda s: float((s == 0).mean())),
                         "three_ball": g.balls_before.apply(lambda s: float((s == 3).mean()))})


def logit_null(df, q_column, ids):
    """타자별 a_i를 mean(sigmoid(logit p + a_i)) = mean(S)로 맞춘 귀무 타자의 기대 Z0·N0."""
    p = df.p_swing.clip(1e-6, 1 - 1e-6).to_numpy(); lp = logit(p)
    r = (df.swing - df.p_swing).to_numpy(); z = 2 * df[q_column].to_numpy() - 1
    rows = {}
    for b, ix in df.groupby("batter_id").indices.items():
        if b not in ids:
            continue
        m = r[ix].mean()
        a = brentq(lambda a: (expit(lp[ix] + a) - p[ix]).mean() - m, -8, 8)
        e = expit(lp[ix] + a) - p[ix]; zz = z[ix]
        rows[b] = {"SA": 100 * m, "Z0_null": 100 * np.mean(e * zz),
                   "N0_null": 100 * np.mean((e - e.mean()) * (zz - zz.mean()))}
    return pd.DataFrame(rows).T


def null_summary(null, observed, kind):
    return {"null_vs_SA_pearson": pearson(null[f"{kind}_null"], null.SA),
            "null_sd": float(null[f"{kind}_null"].std(ddof=1)),
            "observed_sd": float(observed.std(ddof=1)),
            "observed_vs_SA_pearson": pearson(observed, null.SA),
            "observed_minus_null_vs_SA_pearson": pearson(observed - null[f"{kind}_null"], null.SA)}


def half_split(df):
    codes, _ = pd.factorize(df.game_id, sort=True)
    halves = [player_scores(df.loc[codes % 2 == side], min_n=150, side_min=25, side_games=5).set_index("batter_id")
              for side in (0, 1)]
    ids = halves[0].index[halves[0].eligible.astype(bool)].intersection(halves[1].index[halves[1].eligible.astype(bool)])

    def sb(metric, sel):
        r = pearson(halves[0].loc[sel, metric], halves[1].loc[sel, metric]); return 2 * r / (1 + r)

    rng = np.random.default_rng(SEED); out = {"n": int(len(ids))}
    point = {m: sb(m, ids) for m in ("Z0_call", "Z0_free", "N0_free")}
    draws = np.array([[sb("Z0_call", s) - sb(m, s) for m in ("Z0_free", "N0_free")]
                      for s in (ids[rng.integers(0, len(ids), len(ids))] for _ in range(BOOT))])
    for j, m in enumerate(("Z0_free", "N0_free")):
        out[f"Z0_call_minus_{m}"] = {"point": point["Z0_call"] - point[m],
                                     "ci95": [float(x) for x in np.percentile(draws[:, j], [2.5, 97.5])]}
    out["spearman_brown"] = point
    return out


def umpire_season(year):
    df, meta = runner.predictions(year)
    df["batter_id"] = df.batter_id.astype(str)
    recorded = json.loads((HERE / f"results_{year}.json").read_text())["result"]["p_swing_sha256"]
    p_sha = hashlib.sha256(df.p_swing.to_numpy().tobytes()).hexdigest()
    assert p_sha == recorded, f"{year} p_swing가 고정 결과와 다릅니다"
    table = player_scores(df).set_index("batter_id"); q = table[table.eligible.astype(bool)].join(shares(df))
    delta = q.Z0_free - q.Z0_call
    composition = {c: {"delta": pearson(delta, q[c]), "Z0_call": pearson(q.Z0_call, q[c]), "Z0_free": pearson(q.Z0_free, q[c])}
                   for c in ("two_strike", "zero_strike", "three_ball")}
    ids = set(q.index)
    null_call, null_free = logit_null(df, "q_call", ids), logit_null(df, "q_za", ids)
    return {"p_swing_sha256": p_sha, "cache_used": bool(meta.get("cache_used")), "qualified": int(len(q)),
            "count_composition_pearson": composition,
            "point_change": {"sd_delta": float(delta.std(ddof=1)), "mean_Z0_call_se": float(q.Z0_call_se.mean()),
                             "share_abs_delta_gt_1se": float((delta.abs() > q.Z0_call_se).mean()),
                             "share_abs_delta_gt_half_se": float((delta.abs() > .5 * q.Z0_call_se).mean())},
            "half_split": half_split(df),
            "logit_null": {"Z0_call": null_summary(null_call, q.Z0_call.loc[null_call.index], "Z0"),
                           "Z0_free": null_summary(null_free, q.Z0_free.loc[null_free.index], "Z0"),
                           "N0_free": null_summary(null_free, q.N0_free.loc[null_free.index], "N0")}}


def abs_season(year=2026):
    path = runner.ROOT / f"data/metrics/zone_awareness/{year}/pitches.parquet"
    df = pq.ParquetFile(path).read(columns=["batter_id", "game_id", "swing", "p_swing", "p_zone"]).to_pandas()
    df["batter_id"] = df.batter_id.astype(str); df["q_call"] = df.p_zone; df["q_za"] = df.p_zone
    table = player_scores(df).set_index("batter_id"); q = table[table.eligible.astype(bool)]
    null = logit_null(df, "q_za", set(q.index))
    return {"input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "qualified": int(len(q)),
            "logit_null": {"Z0": null_summary(null, q.Z0_call.loc[null.index], "Z0"),
                           "N0": null_summary(null, q.N0_free.loc[null.index], "N0")}}


def main():
    out = {"seed": SEED, "bootstrap": BOOT, "seasons": {str(y): umpire_season(y) for y in (2022, 2023)}}
    out["seasons"]["2026"] = abs_season()
    (HERE / "crosscheck_diagnostics.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
