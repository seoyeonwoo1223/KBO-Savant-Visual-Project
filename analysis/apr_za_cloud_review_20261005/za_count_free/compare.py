"""기존 여섯 ZA 후보의 원시 점수·지원 범위·반분 신뢰도를 비교합니다.

candidate_diagnostics(df, public)는 한 시즌의 투구 표와 batter_id 인덱스의
공개 APR·SA 표(apr, swing_aggression 열)를 받습니다. 전체와 반분의 후보별
적격 집합 및 여섯 후보 공통 집합을 나누어 보고합니다. 반환값은 JSON으로
직렬화할 수 있는 사전이며 정의되지 않거나 유한하지 않은 값은 None입니다.
plus 척도·수축·새 산식을 적용하지 않으며 모형을 다시 적합하지 않습니다.

전체 타자 투구가중평균은 지원 미달도 포함하되 점수가 정의된 타자만 사용하고
그 분모·포함률을 함께 보고합니다. 후보별 상관·점수 SD·평균 SE·순위 이동은
해당 적격 집합에서 계산합니다. 점수 차이는 같은 단위인 Z0_free만 제공합니다.
반분은 시즌 전체의 정렬된 경기 범주 코드 홀짝이며 예측을 고정합니다.
교차적합 학습 표본이 겹치므로 반분 신뢰도는 독립적인 미래 검증이 아닙니다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from metrics import METRICS, player_scores


def _finite(value) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if np.isfinite(numeric) else None


def _coverage(numerator: int, denominator: int) -> float | None:
    return float(numerator / denominator) if denominator else None


def _correlation(left: pd.Series, right: pd.Series) -> dict:
    pairs = pd.concat((left.rename("left"), right.rename("right")), axis=1)
    values = pairs.to_numpy(dtype=float)
    pairs = pairs.loc[np.isfinite(values).all(axis=1)]
    result = {"n": int(len(pairs)), "pearson": None, "spearman": None}
    if len(pairs) < 3:
        return result
    a, b = pairs["left"].to_numpy(), pairs["right"].to_numpy()
    if np.ptp(a) == 0 or np.ptp(b) == 0:
        return result
    result["pearson"] = _finite(np.clip(np.corrcoef(a, b)[0, 1], -1, 1))
    ranks = pairs.rank(method="average")
    result["spearman"] = _finite(np.clip(np.corrcoef(ranks["left"], ranks["right"])[0, 1], -1, 1))
    return result


def _weighted_mean(table: pd.DataFrame, metric: str, total_pitches: int) -> dict:
    values = table[metric].to_numpy(dtype=float)
    finite = np.isfinite(values)
    weights = table["n"].to_numpy(dtype=float)[finite]
    denominator = int(weights.sum())
    return {
        "value": _finite(np.dot(values[finite], weights) / denominator) if denominator else None,
        "n_players": int(finite.sum()), "n_pitches": denominator,
        "pitch_coverage": _coverage(denominator, total_pitches),
    }


def _candidate_statistics(table: pd.DataFrame, metric: str, ids: pd.Index,
                          public: pd.DataFrame, n_qualified: int) -> dict:
    subset = table.loc[ids]
    scores = subset[metric].astype(float)
    ses = subset[f"{metric}_se"].astype(float)
    ses = ses.loc[np.isfinite(ses)]
    benchmark = subset["Z0_call"].astype(float)
    rank_delta = (scores.rank(ascending=False, method="average")
                  - benchmark.rank(ascending=False, method="average")).abs()
    total_pitches = int(subset["n"].sum())
    result = {
        "n": int(len(subset)),
        "coverage_of_qualified": _coverage(len(subset), n_qualified),
        "n_pitches": total_pitches,
        "score_sd_ddof1": _finite(scores.std(ddof=1)) if len(scores) > 1 else None,
        "mean_se": _finite(ses.mean()) if len(ses) else None,
        "n_finite_se": int(len(ses)),
        "q_degenerate_n": int(subset["q_degenerate"].astype(bool).sum()),
        "support_pitch_weighted_mean": _weighted_mean(subset, metric, total_pitches)["value"],
        "correlations": {
            "swing_aggression": _correlation(scores, public["swing_aggression"].reindex(ids)),
            "apr": _correlation(scores, public["apr"].reindex(ids)),
            "Z0_call": _correlation(scores, benchmark),
        },
        "max_abs_rank_change_vs_Z0_call": _finite(rank_delta.max()) if len(subset) else None,
        "mean_abs_point_delta_vs_Z0_call": None,
    }
    if metric == "Z0_free" and len(subset):
        result["mean_abs_point_delta_vs_Z0_call"] = _finite((scores - benchmark).abs().mean())
    return result


def _eligible_ids(table: pd.DataFrame, metric: str) -> pd.Index:
    return table.index[table[f"{metric}_eligible"].astype(bool)]


def _common_ids(table: pd.DataFrame) -> pd.Index:
    mask = np.ones(len(table), dtype=bool)
    for metric in METRICS:
        mask &= table[f"{metric}_eligible"].to_numpy(dtype=bool)
    return table.index[mask]


def _reliability(first: pd.DataFrame, second: pd.DataFrame, metric: str, ids: pd.Index) -> dict:
    correlation = _correlation(first.loc[ids, metric].astype(float), second.loc[ids, metric].astype(float))
    pearson = correlation["pearson"]
    # 음의 신뢰도를 임의로 0으로 자르지 않으며 r=-1의 정의되지 않은 보정만 비웁니다.
    brown = _finite(2 * pearson / (1 + pearson)) if pearson is not None and pearson > -1 else None
    return {"n": correlation["n"], "pearson": pearson,
            "spearman_brown": brown, "spearman": correlation["spearman"]}


def _paired_reliability(first: pd.DataFrame, second: pd.DataFrame, metric: str,
                        ids: pd.Index, n_qualified: int) -> dict:
    return {
        "n": int(len(ids)),
        "coverage_of_both_half_qualified": _coverage(len(ids), n_qualified),
        "candidate": _reliability(first, second, metric, ids),
        "Z0_call_same_ids": _reliability(first, second, "Z0_call", ids),
    }


def candidate_diagnostics(df: pd.DataFrame, public: pd.DataFrame) -> dict:
    """한 시즌의 고정 예측과 공개 APR·SA로 비교 사전을 반환합니다.

    반환 구조는 full/{candidates, common_support, all_player_pitch_weighted_means}
    및 half_split/{candidates, common_support}입니다. 공개값이 없는 ID도 지원
    표본 수에 포함하고 APR·SA 상관은 유한한 대응값이 있는 ID만 사용합니다.
    입력 표와 공개값을 변경하지 않습니다. 전체 기준은 n>=300, 안팎>=50구·
    10경기이며 반분 기준은 n>=150, 안팎>=25구·5경기입니다.
    """
    missing = [name for name in ("apr", "swing_aggression") if name not in public]
    if missing:
        raise ValueError(f"Missing public columns: {', '.join(missing)}")
    if not public.index.is_unique or public.index.hasnans:
        raise ValueError("public batter_id index must be unique and nonmissing")
    if "season" in df and df["season"].nunique(dropna=False) > 1:
        raise ValueError("candidate_diagnostics requires a single season")
    public_values = public.loc[:, ["apr", "swing_aggression"]].apply(pd.to_numeric, errors="coerce")
    table = player_scores(df).set_index("batter_id")
    n_qualified = int(table["eligible"].astype(bool).sum())
    common = _common_ids(table)
    full = {
        "n_pitches": int(len(df)), "n_players": int(len(table)), "n_qualified": n_qualified,
        "n_public_matched": int(table.index.isin(public.index).sum()),
        "thresholds": {"min_n": 300, "side_min": 50, "side_games": 10},
        "all_player_pitch_weighted_means": {
            metric: _weighted_mean(table, metric, len(df)) for metric in METRICS
        },
        "candidates": {
            metric: _candidate_statistics(table, metric, _eligible_ids(table, metric), public_values, n_qualified)
            for metric in METRICS
        },
        "common_support": {
            "n": int(len(common)), "coverage_of_qualified": _coverage(len(common), n_qualified),
            "candidates": {
                metric: _candidate_statistics(table, metric, common, public_values, n_qualified)
                for metric in METRICS
            },
        },
    }
    # 시즌 전체에서 경기를 먼저 정렬해 타자별로 다른 홀짝 분할이 생기지 않게 합니다.
    codes, games = pd.factorize(df["game_id"], sort=True)
    halves = [df.loc[codes % 2 == side] for side in (0, 1)]
    half_tables = [player_scores(half, min_n=150, side_min=25, side_games=5).set_index("batter_id")
                   for half in halves]
    first, second = half_tables
    both_qualified = first.index[first["eligible"].astype(bool)].intersection(
        second.index[second["eligible"].astype(bool)], sort=False)
    both_common = _common_ids(first).intersection(_common_ids(second), sort=False)
    half_split = {
        "rule": "시즌 전체 정렬 경기 범주 코드의 0-based 짝수/홀수",
        "limitations": "예측 고정·겹치는 교차적합 학습 표본: 독립적인 미래 검증이 아닌 서술적 반분 신뢰도",
        "thresholds": {"min_n": 150, "side_min": 25, "side_games": 5},
        "n_games": [int(np.sum(np.arange(len(games)) % 2 == side)) for side in (0, 1)],
        "n_pitches": [int(len(half)) for half in halves],
        "n_both_half_qualified": int(len(both_qualified)),
        "candidates": {},
        "common_support": {
            "n": int(len(both_common)),
            "coverage_of_both_half_qualified": _coverage(len(both_common), len(both_qualified)),
            "candidates": {},
        },
    }
    for metric in METRICS:
        ids = _eligible_ids(first, metric).intersection(_eligible_ids(second, metric), sort=False)
        half_split["candidates"][metric] = _paired_reliability(first, second, metric, ids, len(both_qualified))
        half_split["common_support"]["candidates"][metric] = _paired_reliability(
            first, second, metric, both_common, len(both_qualified))
    return {"full": full, "half_split": half_split}
