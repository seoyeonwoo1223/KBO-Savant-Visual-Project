"""Z0_call·Z0_free에 한정하여 현행 ZA+ 척도의 민감도를 확인합니다.

plus_sensitivity(df, public)는 metrics의 필수 투구 열과 batter_id 인덱스의
public를 받습니다. public의 za_plus는 필수이며 zj_per_100, zj_se,
za_percentile이 있으면 baseline의 추가 일치 검산에 사용합니다.

각 Z0의 입력과 현행 SE를 6자리로 반올림한 뒤 운영 _plus_index를 그대로
호출합니다. 예측 확률 자체는 반올림하지 않습니다. SE는 metrics의 경기
G/(G-1) 보정을 되돌린 2*SE*sqrt((G-1)/G)이며 G=1은 0입니다.
M=100*E[(2S-1)(2q-1)]과 중심=100*E[2(S-p)(2q-1)]은 후보별 원시
투구에서 따로 계산합니다. N0·D·P0에 이 분모를 재사용하지 않습니다.

반환 사전은 JSON으로 직렬화할 수 있고 유한하지 않은 값은 None입니다.
모형을 적합하거나 운영 파일을 변경하지 않습니다. 현행 SE 관례를 재현하는
척도 민감도이며 새로운 후보의 최종 채택 또는 새 수축의 검증이 아닙니다.
visualbaseball(src)가 import 가능한 환경에서 호출해야 합니다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from metrics import player_scores


def _finite(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _match_errors(calculated: pd.Series, published: pd.Series) -> dict:
    pairs = pd.concat((calculated.rename("calculated"), published.rename("published")), axis=1)
    values = pairs.to_numpy(dtype=float)
    pairs = pairs.loc[np.isfinite(values).all(axis=1)]
    errors = (pairs["calculated"] - pairs["published"]).abs()
    return {
        "n": int(len(pairs)),
        "max_abs_error": _finite(errors.max()) if len(errors) else None,
        "mean_abs_error": _finite(errors.mean()) if len(errors) else None,
        "n_errors_gt_1e_6": int((errors > 1e-6 + 32 * np.finfo(float).eps).sum()),
    }


def _build_index(df: pd.DataFrame, scores: pd.DataFrame, metric: str, q_column: str) -> tuple[dict, pd.DataFrame]:
    # 운영 함수는 6자리 타자 입력으로 k를 추정하고 원시 투구 평균을 중심으로 사용합니다.
    from visualbaseball.zone_decision import _plus_index, r6

    players = []
    for batter_id, row in scores.iterrows():
        games = int(row["n_games"])
        old_se = 2 * float(row[f"{metric}_se"]) * np.sqrt((games - 1) / games) if games > 1 else 0.
        players.append({
            "batter_id": str(batter_id), "pitches_seen": int(row["n"]),
            "qualified_300": bool(row["eligible"]),
            "zj_per_100": r6(2 * row[metric]), "zj_se": r6(old_se),
        })
    columns = ["zj_per_100", "zj_se", "za_plus", "za_percentile"]
    if not len(df):
        return {"available": False, "reason": "빈 투구 표본", "M": None,
                "league_center": None, "k": None, "n_players": 0, "n_qualified": 0,
                "qualified_sd_ddof1": None, "pitch_weighted_mean": None}, pd.DataFrame(index=scores.index, columns=columns)
    swing = df["swing"].to_numpy(dtype=float)
    p = df["p_swing"].to_numpy(dtype=float)
    z = 2 * df[q_column].to_numpy(dtype=float) - 1
    level = 100 * float(np.mean((2 * swing - 1) * z))
    centre = 100 * float(np.mean(2 * (swing - p) * z))
    n = scores["n"].to_numpy(dtype=float)
    qualified = scores["eligible"].to_numpy(dtype=bool)
    if level == 0:
        # M=0인 척도는 정의되지 않으므로 임의의 대체 분모를 사용하지 않습니다.
        for player in players:
            player.update(za_plus=None, za_percentile=None)
        k = None
    else:
        k = _plus_index(players, "zj_per_100", "zj_se", level, centre, "za_plus", "za_percentile")
    indexed = pd.DataFrame(players, index=scores.index).loc[:, columns]
    plus = pd.to_numeric(indexed["za_plus"], errors="coerce").to_numpy(dtype=float)
    finite = np.isfinite(plus)
    qualified_plus = plus[qualified & finite]
    weighted = float(np.dot(plus[finite], n[finite]) / n[finite].sum()) if finite.any() else None
    return {
        "available": bool(level != 0), "reason": None if level != 0 else "M=0으로 ZA+ 척도 정의 불가",
        "M": r6(level), "M_positive": bool(level > 0), "league_center": r6(centre), "k": _finite(k),
        "n_players": int(len(players)), "n_qualified": int(qualified.sum()),
        "qualified_sd_ddof1": _finite(np.std(qualified_plus, ddof=1)) if len(qualified_plus) > 1 else None,
        "pitch_weighted_mean": _finite(weighted),
    }, indexed


def _rank_comparison(old: pd.Series, new: pd.Series) -> dict:
    pairs = pd.concat((old.rename("old"), new.rename("new")), axis=1)
    pairs = pairs.loc[np.isfinite(pairs.to_numpy(dtype=float)).all(axis=1)]
    ranks = pairs.rank(method="average", ascending=False)
    correlation = None
    if len(pairs) >= 3 and np.ptp(ranks["old"]) > 0 and np.ptp(ranks["new"]) > 0:
        correlation = _finite(np.clip(np.corrcoef(ranks["old"], ranks["new"])[0, 1], -1, 1))
    delta = (pairs["new"] - pairs["old"]).abs()
    rank_delta = (ranks["new"] - ranks["old"]).abs()
    return {
        "n": int(len(pairs)), "rank_spearman": correlation,
        "max_abs_point_delta": _finite(delta.max()) if len(delta) else None,
        "mean_abs_point_delta": _finite(delta.mean()) if len(delta) else None,
        "max_abs_rank_change": _finite(rank_delta.max()) if len(rank_delta) else None,
    }


def plus_sensitivity(df: pd.DataFrame, public: pd.DataFrame) -> dict:
    """Z0_call baseline 일치와 Z0_free의 후보별 ZA+ 척도 민감도를 반환합니다.

    candidates에는 각각 k, M, 중심, 적격 점수 SD가 있습니다. comparison은
    전체·적격 집합의 old/new 순위와 점수 차이를 제공합니다. players는 후보별
    반올림 입력·현행 SE·ZA+·백분위를 보관하며 public의 APR는 사용하지 않습니다.
    """
    if "za_plus" not in public:
        raise ValueError("public must provide za_plus")
    if not public.index.is_unique or public.index.hasnans:
        raise ValueError("public batter_id index must be unique and nonmissing")
    if "season" in df and df["season"].nunique(dropna=False) > 1:
        raise ValueError("plus_sensitivity requires a single season")
    scores = player_scores(df).set_index("batter_id")
    old_meta, old = _build_index(df, scores, "Z0_call", "q_call")
    new_meta, new = _build_index(df, scores, "Z0_free", "q_za")
    published = pd.to_numeric(public["za_plus"], errors="coerce").round(6)
    baseline = {"za_plus": _match_errors(old["za_plus"].astype(float), published.reindex(scores.index))}
    for column in ("zj_per_100", "zj_se", "za_percentile"):
        if column in public:
            published_column = pd.to_numeric(public[column], errors="coerce").round(6)
            baseline[column] = _match_errors(old[column].astype(float), published_column.reindex(scores.index))
    baseline_checks = list(baseline.values())
    baseline["tolerance"] = 5e-7
    baseline["pass"] = bool(len(scores) > 0 and all(
        check["n"] == len(scores) and check["max_abs_error"] is not None
        and check["max_abs_error"] <= baseline["tolerance"] for check in baseline_checks
    ))
    qualified = scores.index[scores["eligible"].astype(bool)]
    k_delta = new_meta["k"] - old_meta["k"] if new_meta["k"] is not None and old_meta["k"] is not None else None
    m_delta = new_meta["M"] - old_meta["M"] if new_meta["M"] is not None and old_meta["M"] is not None else None
    player_output = []
    for batter_id, row in scores.iterrows():
        record = {"batter_id": str(batter_id), "n": int(row["n"]), "n_games": int(row["n_games"]),
                  "qualified_300": bool(row["eligible"])}
        for label, indexed in (("Z0_call", old), ("Z0_free", new)):
            record[label] = {column: _finite(indexed.loc[batter_id, column]) for column in indexed.columns}
        player_output.append(record)
    return {
        "scope": ["Z0_call", "Z0_free"],
        "production_convention": {
            "source": "src/visualbaseball/zone_decision.py:_plus_index, profile_summary, write_web",
            "rounding_decimals": 6, "input": "2*Z0", "se": "2*SE_Gcorrected*sqrt((G-1)/G); G=1이면 0",
            "denominator": "후보별 고유 M이며 N0/D/P0에 재사용하지 않음", "uses_G_correction": False,
        },
        "baseline_reproduction": baseline,
        "candidates": {"Z0_call": old_meta, "Z0_free": new_meta},
        "comparison": {
            "k_delta": _finite(k_delta), "M_delta": _finite(m_delta),
            "all_players": _rank_comparison(old["za_plus"].astype(float), new["za_plus"].astype(float)),
            "qualified": _rank_comparison(old.loc[qualified, "za_plus"].astype(float), new.loc[qualified, "za_plus"].astype(float)),
        },
        "players": player_output,
    }
