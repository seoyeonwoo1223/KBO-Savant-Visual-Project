"""입력 해시를 검산하고 적합된 예측의 ZA 비교를 재생성한다."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

import run_experiment as experiment
from compare import candidate_diagnostics
from metrics import METRICS, player_scores
from plus_sensitivity import plus_sensitivity

ROOT, OUT = experiment.ROOT, experiment.OUT


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_verified(year):
    """캐시는 공개 집계 읽기 직전의 입력 목록과 runner 해시에 묶인다."""
    payload = json.loads((OUT/f"results_{year}.json").read_text())
    for relative, expected in payload["inputs"].items():
        path = ROOT/relative
        assert path.stat().st_size == expected["bytes"], relative
        assert digest(path) == expected["sha256"], relative
    assert payload["result"]["baseline_reproduction"]["pass"]
    experiment.INPUTS.clear()
    if year >= experiment.zd.ABS_FIRST_SEASON:
        df, _ = experiment.predictions(year)
        assert (df.q_call == df.q_za).all()
    else:
        key_inputs = dict(payload["inputs"])
        del key_inputs[f"web/data/zone_awareness/{year}/leaderboard.json"]
        key = hashlib.sha256(json.dumps({
            "inputs": key_inputs, "runner_sha256": digest(Path(experiment.__file__)),
            "fields": experiment.zd.pzone_fields(year), "model": experiment.zd.MODEL_VERSION,
            "seeds": experiment.zd.PZONE_SEEDS,
        }, sort_keys=True).encode()).hexdigest()
        with np.load(OUT/"cache"/f"predictions_{year}.npz", allow_pickle=False) as cache:
            assert str(cache["input_key"]) == key, "적합 캐시와 입력/runner가 다름"
            rows, metadata = experiment.load_human(year)
            assert len(rows) == payload["result"]["metadata"]["eligible_rows"]
            assert metadata["quality"] == payload["result"]["metadata"]["quality"]
            df = pd.DataFrame(rows)
            df["swing"] = (df.decision_type == "Swing").astype(int)
            for field in ("p_swing", "raw_p_swing", "q_call", "q_za", "fold"):
                df[field] = cache[field]
            assert float(cache["count_control"]) == 0.
    df["batter_id"] = df.batter_id.astype(str)
    df["season"] = year
    assert len(df) == payload["result"]["baseline_reproduction"]["pitches"]
    assert hashlib.sha256(df.p_swing.to_numpy().tobytes()).hexdigest() == payload["result"]["p_swing_sha256"]
    public_payload = json.loads((ROOT/f"web/data/zone_awareness/{year}/leaderboard.json").read_text())
    public = pd.DataFrame(public_payload["players"]).set_index("batter_id")
    public.index = public.index.astype(str)
    return df, public, payload


def paired_call_cost(df):
    """추가 기술통계: 고정 예측의 Take log loss 차이와 경기 군집 SE."""
    takes = df.loc[df.swing == 0]
    y = (takes.event == "CalledStrike").to_numpy(float)
    losses = {}
    for field in ("q_call", "q_za"):
        p = takes[field].to_numpy(float)
        losses[field] = -(y*np.log(p)+(1-y)*np.log1p(-p))
    delta = losses["q_za"]-losses["q_call"]
    mean = float(delta.mean())
    codes, games = pd.factorize(takes.game_id, sort=False)
    totals = np.bincount(codes, weights=delta-mean)
    g = len(games)
    se = float(np.sqrt(g/(g-1)*np.dot(totals, totals))/len(takes))
    return {"take_n": len(takes), "n_games": g, "free_minus_call": mean,
            "fixed_prediction_game_cluster_se": se,
            "descriptive_normal_95_interval": [mean-1.96*se, mean+1.96*se],
            "limitation": "적합 뒤 추가한 기술통계. 모형 추정 불확실성/겹치는 학습 표본은 포함하지 않으며 채택 gate가 아님"}


def spatial_summary(df):
    """실제 관측 위치 구성의 지역 요약이며 물리 축 단조성 검증이 아니다."""
    rows = []
    for region, group in df.groupby("region", sort=True, observed=True):
        rows.append({"region": str(region), "n": len(group),
                     "q_call_mean": float(group.q_call.mean()),
                     "q_za_mean": float(group.q_za.mean()),
                     "q_za_median": float(group.q_za.median()),
                     "q_za_p10": float(group.q_za.quantile(.1)),
                     "q_za_p90": float(group.q_za.quantile(.9)),
                     "mean_z_za": float((2*group.q_za-1).mean()),
                     "side_flip_fraction": float(((group.q_call >= .5) != (group.q_za >= .5)).mean())})
    return rows


def main():
    output = {"base_commit": experiment.BASE,
              "preregistration_commit": "2036e4dad9fa60ff638873bfd81e796425c66146",
              "interpretation": {
                  "p_swing": "카운트와 기존 q_call 기반 isotonic 보정을 유지한 동일 예측",
                  "q_za": "명시적 카운트 입력을 제거한 Take-only 구심 콜 모형; ABS는 저장 예측 재사용",
                  "pooled_scores": "results 파일의 scores는 시즌 전체를 한 집단으로 계산; 타자별 중심화 평균과 다름",
                  "all_player_means": "diagnostics.full.all_player_pitch_weighted_means는 타자별 계산 뒤 투구가중평균",
                  "half_split": "고정 예측·겹치는 학습 표본의 서술적 반분이며 미래 독립 검증이 아님",
              }, "seasons": {}}
    flat = []
    for year in (2022, 2023, 2026):
        df, public, payload = read_verified(year)
        diagnostics = candidate_diagnostics(df, public)
        sensitivity = plus_sensitivity(df, public)
        assert sensitivity["baseline_reproduction"]["pass"]
        item = {"baseline_reproduction": payload["result"]["baseline_reproduction"],
                "q_change": payload["result"]["q_change"],
                "calibration": payload["result"]["calibration"],
                "paired_call_cost": paired_call_cost(df),
                "spatial_summary": spatial_summary(df),
                "diagnostics": diagnostics, "ZA_plus_sensitivity": sensitivity}
        output["seasons"][str(year)] = item
        for metric in METRICS:
            full = diagnostics["full"]["candidates"][metric]
            half = diagnostics["half_split"]["candidates"][metric]
            flat.append({"season": year, "candidate": metric, "n": full["n"],
                         "coverage": full["coverage_of_qualified"], "SD": full["score_sd_ddof1"],
                         "mean_SE": full["mean_se"],
                         "SA_Pearson": full["correlations"]["swing_aggression"]["pearson"],
                         "APR_Spearman": full["correlations"]["apr"]["spearman"],
                         "Z0_call_Spearman": full["correlations"]["Z0_call"]["spearman"],
                         "half_n": half["n"], "half_Pearson": half["candidate"]["pearson"],
                         "half_SB": half["candidate"]["spearman_brown"],
                         "same_ids_Z0_call_SB": half["Z0_call_same_ids"]["spearman_brown"]})
        table = player_scores(df).set_index("batter_id")
        table["batter_name"] = public.batter_name
        table["raw_delta"] = table.Z0_free-table.Z0_call
        for metric in ("Z0_call", "Z0_free"):
            table[f"{metric}_rank_qualified"] = table.loc[table.eligible, metric].rank(ascending=False, method="average")
        table["rank_delta"] = table.Z0_free_rank_qualified-table.Z0_call_rank_qualified
        table.reset_index().to_csv(OUT/f"player_comparison_{year}.csv", index=False, float_format="%.10f")
        print(year, "후보 비교 완료", "전체 적격", diagnostics["full"]["n_qualified"], flush=True)
    output["implementation_sha256"] = {name: digest(OUT/name) for name in (
        "run_experiment.py", "metrics.py", "compare.py", "plus_sensitivity.py", "summarize.py")}
    (OUT/"comparison.json").write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False)+"\n")
    pd.DataFrame(flat).to_csv(OUT/"candidate_comparison.csv", index=False, float_format="%.10f")


if __name__ == "__main__":
    main()
