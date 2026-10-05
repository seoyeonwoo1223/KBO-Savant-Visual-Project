"""고정된 교차적합 투구 예측으로 기존 ZA 후보를 계산합니다.

``player_scores(df)``는 타자별 한 행, ``score_summary(df)``는 입력 전체를
하나의 집단으로 계산합니다. 필수 열은 game_id, batter_id, swing(0/1),
p_swing, q_call, q_za입니다. region 등 선택 열은 계산에 사용하지 않습니다.
모형 적합·점수 수축·파일 변경·ZA+ 분모 적용 없이 원시 점수와 SE를
percentage-point 단위로 반환합니다.

r=S-p_swing, z=2*q_za-1일 때 Z0_free=100*E(r*z),
N0_free=100*Cov_n(r,z), D_bin=100*(E[r|q>=.5]-E[r|q<.5]),
D_q=100*(E(q*r)/E(q)-E((1-q)*r)/E(1-q)),
P0_free=100*E((2*S-1)*z)입니다. Z0_call은 q_call을 사용합니다.
Cov_n의 분모는 n이며 n-1 보정을 적용하지 않습니다.

SE는 제공된 예측을 고정하고 평균·비율 분모의 공동 추정을 포함한 경험적
영향함수를 경기별로 합산한 뒤 G/(G-1)을 적용합니다. 모형 추정 불확실성은
포함하지 않으며, 교차적합 학습 표본이 겹치는 문제도 해소하지 않습니다.

D-bin의 안팎은 q_za >= .5 / < .5입니다. 지원 기준은 전체 min_n구,
안팎 각각 side_min구·side_games경기입니다. D-q는 q와 1-q의 Kish ESS를
사용하며 전체 min_n구, 양쪽 ESS >= side_min, .1 <= mean(q) <= .9를
요구합니다. 지원 기준 미달이어도 점수를 반환하며 정의되지 않은 비율과
2경기 미만의 SE는 NaN입니다. 상수 q의 퇴화 여부를 별도로 기록하고,
요청된 지원 기준에는 q 분산 조건을 추가하지 않습니다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


METRICS = ("Z0_call", "Z0_free", "N0_free", "D_bin", "D_q", "P0_free")
REQUIRED = ("game_id", "batter_id", "swing", "p_swing", "q_call", "q_za")
SUPPORT_COLUMNS = (
    "n", "n_games", "eligible", "se_available", "rbar", "qbar", "variance_q",
    "q_degenerate", "n_in", "n_out", "games_in", "games_out", "ess_in",
    "ess_out", "q_weight_in", "q_weight_out", "n_q_in_positive",
    "n_q_out_positive", "games_q_in_positive", "games_q_out_positive",
    "ess_q_in", "ess_q_out", "D_bin_support", "D_q_support",
)
OUTPUT_COLUMNS = ["batter_id", *SUPPORT_COLUMNS]
for _metric in METRICS:
    OUTPUT_COLUMNS.extend((_metric, f"{_metric}_se", f"{_metric}_eligible"))


def _validate(df: pd.DataFrame) -> None:
    missing = [name for name in REQUIRED if name not in df]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    if df.loc[:, ["game_id", "batter_id"]].isna().any().any():
        raise ValueError("game_id and batter_id must not be missing")
    for name in ("swing", "p_swing", "q_call", "q_za"):
        try:
            values = df[name].to_numpy(dtype=float)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be numeric") from exc
        if not np.isfinite(values).all():
            raise ValueError(f"{name} must be finite")
        if np.any((values < 0) | (values > 1)):
            raise ValueError(f"{name} must lie in [0, 1]")
        if name == "swing" and np.any((values != 0) & (values != 1)):
            raise ValueError("swing must be binary")


def _ess(weights: np.ndarray) -> float:
    squared = float(np.dot(weights, weights))
    return float(weights.sum() ** 2 / squared) if squared > 0 else 0.0


def _functional(df: pd.DataFrame) -> tuple[dict, dict[str, np.ndarray]]:
    n = len(df)
    if n == 0:
        raise ValueError("A cohort must contain at least one pitch")
    swing = df["swing"].to_numpy(dtype=float)
    r = swing - df["p_swing"].to_numpy(dtype=float)
    q = df["q_za"].to_numpy(dtype=float)
    z = 2 * q - 1
    z_call = 2 * df["q_call"].to_numpy(dtype=float) - 1
    rbar, qbar, zbar = float(r.mean()), float(q.mean()), float(z.mean())
    inside = q >= .5
    outside = ~inside
    scores: dict[str, float] = {}
    influences: dict[str, np.ndarray] = {}
    for name, observation in (
        ("Z0_call", r * z_call), ("Z0_free", r * z),
        ("P0_free", (2 * swing - 1) * z),
    ):
        mean = float(observation.mean())
        scores[name] = 100 * mean
        influences[name] = 100 * (observation - mean)
    centred_product = (r - rbar) * (z - zbar)
    covariance = float(centred_product.mean())
    scores["N0_free"] = 100 * covariance
    influences["N0_free"] = 100 * (centred_product - covariance)
    if inside.any() and outside.any():
        rin, rout = float(r[inside].mean()), float(r[outside].mean())
        scores["D_bin"] = 100 * (rin - rout)
        influences["D_bin"] = 100 * (
            inside / inside.mean() * (r - rin)
            - outside / outside.mean() * (r - rout)
        )
    else:
        scores["D_bin"] = float("nan")
        influences["D_bin"] = np.full(n, np.nan)
    if qbar > 0 and qbar < 1:
        rq_in = float(np.dot(q, r) / q.sum())
        rq_out = float(np.dot(1 - q, r) / (1 - q).sum())
        scores["D_q"] = 100 * (rq_in - rq_out)
        influences["D_q"] = 100 * (
            q / qbar * (r - rq_in)
            - (1 - q) / (1 - qbar) * (r - rq_out)
        )
    else:
        scores["D_q"] = float("nan")
        influences["D_q"] = np.full(n, np.nan)
    scores.update(rbar=rbar, qbar=qbar, variance_q=float(np.var(q, ddof=0)))
    return scores, influences


def pitch_influence_functions(df: pd.DataFrame) -> pd.DataFrame:
    """입력 행 인덱스를 유지하며 한 집단의 경험적 영향함수를 반환합니다.

    열별 평균은 부동소수점 오차 범위에서 0입니다. IF[i]는
    (1-epsilon)F + epsilon*delta_i에서 점수를 미분한 값입니다.
    타자별로 나누지 않으므로 필요한 집단별로 호출해야 합니다.
    """
    _validate(df)
    _, influences = _functional(df)
    return pd.DataFrame(influences, index=df.index).loc[:, METRICS]


def _cluster_se(influence: np.ndarray, codes: np.ndarray, games: int) -> float:
    if games < 2 or not np.isfinite(influence).all():
        return float("nan")
    totals = np.bincount(codes, weights=influence, minlength=games)
    return float(np.sqrt(games / (games - 1) * np.dot(totals, totals)) / len(influence))


def _summarize(df: pd.DataFrame, min_n: int, side_min: int, side_games: int) -> dict:
    scores, influences = _functional(df)
    q = df["q_za"].to_numpy(dtype=float)
    inside, outside = q >= .5, q < .5
    codes, unique_games = pd.factorize(df["game_id"], sort=False)
    n, games = len(df), len(unique_games)
    n_in, n_out = int(inside.sum()), int(outside.sum())
    games_in = int(np.unique(codes[inside]).size)
    games_out = int(np.unique(codes[outside]).size)
    ess_in, ess_out = _ess(q), _ess(1 - q)
    enough = bool(n >= min_n)
    bin_support = bool(
        n_in >= side_min and n_out >= side_min
        and games_in >= side_games and games_out >= side_games
    )
    # 평균 계산 후 qbar/ESS 경계의 소수 표현에서 수 ulp 반올림이 가능합니다.
    tolerance = 32 * np.finfo(float).eps
    q_support = bool(
        ess_in >= side_min - tolerance * max(1, side_min)
        and ess_out >= side_min - tolerance * max(1, side_min)
        and .1 - tolerance <= scores["qbar"] <= .9 + tolerance
    )
    summary = {
        "n": n, "n_games": games, "eligible": enough, "se_available": games >= 2,
        "rbar": scores["rbar"], "qbar": scores["qbar"], "variance_q": scores["variance_q"],
        "q_degenerate": bool(np.all(q == q[0])),
        "n_in": n_in, "n_out": n_out, "games_in": games_in, "games_out": games_out,
        "ess_in": float(n_in), "ess_out": float(n_out),
        "q_weight_in": float(q.sum()), "q_weight_out": float((1 - q).sum()),
        "n_q_in_positive": int((q > 0).sum()), "n_q_out_positive": int((q < 1).sum()),
        "games_q_in_positive": int(np.unique(codes[q > 0]).size),
        "games_q_out_positive": int(np.unique(codes[q < 1]).size),
        "ess_q_in": ess_in, "ess_q_out": ess_out,
        "D_bin_support": bin_support, "D_q_support": q_support,
    }
    for name in METRICS:
        summary[name] = scores[name]
        summary[f"{name}_se"] = _cluster_se(influences[name], codes, games)
        supported = bin_support if name == "D_bin" else q_support if name == "D_q" else True
        summary[f"{name}_eligible"] = bool(enough and supported and np.isfinite(scores[name]))
    return summary


def _check_thresholds(min_n: int, side_min: int, side_games: int) -> None:
    for name, value in (("min_n", min_n), ("side_min", side_min), ("side_games", side_games)):
        if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 1:
            raise ValueError(f"{name} must be a positive integer")


def score_summary(df: pd.DataFrame, min_n: int = 300, side_min: int = 50, side_games: int = 10) -> dict:
    """전체 행을 한 집단으로 계산하며 빈 입력에는 ValueError를 발생시킵니다."""
    _check_thresholds(min_n, side_min, side_games)
    _validate(df)
    return _summarize(df, min_n, side_min, side_games)


def player_scores(df: pd.DataFrame, min_n: int = 300, side_min: int = 50, side_games: int = 10) -> pd.DataFrame:
    """입력을 정렬·변경하지 않고 타자별 점수·지원 정보·SE를 반환합니다.

    타자 ID 값과 최초 등장 순서를 유지합니다. 시즌별 점수에는 한 시즌만
    입력해야 합니다. 빈 입력은 정해진 출력 열만 있는 빈 표를 반환합니다.
    """
    _check_thresholds(min_n, side_min, side_games)
    _validate(df)
    rows = []
    for batter_id, group in df.groupby("batter_id", sort=False, observed=True):
        rows.append({"batter_id": batter_id, **_summarize(group, min_n, side_min, side_games)})
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
