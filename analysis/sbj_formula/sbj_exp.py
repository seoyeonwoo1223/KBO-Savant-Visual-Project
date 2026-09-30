"""SBJ C0·C1 실험 공용 하네스 (읽기 전용). 기준은 gates.md.

운영 `score_crossfit()`의 p_swing(보정 게이트 포함)·p_zone 부분만 떼어 설정을 바꿔 다시 적합한다.
사건·가치 모델(DV)은 적합하지 않는다.
"""
import pickle
import time
from pathlib import Path

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.model_selection import GroupKFold

from visualbaseball import plate_decision_v1 as old
from visualbaseball import zone_decision as zd

ROOT = Path(__file__).resolve().parents[2]
CACHE = Path("/tmp/sbj_formula_cache")
RS = old.RANDOM_STATE


def rows_for(season):
    """운영 load_rows 결과를 캐시한다(시즌당 1회)."""
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"rows_{season}.pkl"
    if path.exists():
        return pickle.loads(path.read_bytes())
    rows, _ = zd.load_rows(ROOT, season)
    path.write_bytes(pickle.dumps(rows, protocol=pickle.HIGHEST_PROTOCOL))
    return rows


def ordered_folds(rows):
    """score_crossfit과 같은 순서(블록별 test 행을 이어 붙임)의 행과 fold 번호."""
    dates = np.array(sorted({r["game_id"][:8] for r in rows}))
    ordered, fold = [], []
    for f, block in enumerate(np.array_split(dates, zd.CROSSFIT_FOLDS)):
        held = set(block)
        test = [r for r in rows if r["game_id"][:8] in held]
        ordered.extend(test); fold.extend([f] * len(test))
    return ordered, np.array(fold), [set(b) for b in np.array_split(dates, zd.CROSSFIT_FOLDS)]


class Ensemble:
    """seed 여러 개의 확률 평균. seed 1개면 단일 모델과 같다."""

    def __init__(self, factory, seeds, early_stopping):
        self.factory, self.seeds, self.es = factory, list(seeds), early_stopping

    def fit(self, x, y):
        self.models = [zd.fit_model(self.factory().set_params(random_state=s, early_stopping=self.es), x, y) for s in self.seeds]
        return self

    def proba(self, x):
        return np.mean([m.predict_proba(x)[:, list(m.classes_).index(1)] for m in self.models], axis=0)


def pswing_fit_predict(train, test, seeds=(RS,), es="auto", calibration="gate"):
    """fit_predict()의 propensity + 보정 게이트와 같은 절차.

    calibration: "gate"(운영: 80/20 날짜 게이트가 적용 여부 결정), "always"(항상 적용), "never"(보정 없음).
    """
    sa, sb = zd.encode(train, test, zd.PSWING_CATEGORICAL)
    actions = np.array([r["decision_type"] == "Swing" for r in train], dtype=int)
    make = lambda: Ensemble(zd.pswing_classifier, seeds, es)
    raw_p = make().fit(sa, actions).proba(sb)
    p = raw_p.copy()
    if calibration == "never":
        return p, False
    groups = np.array([r["game_id"] for r in train]); folds = min(3, len(set(groups)))
    oof = np.empty(len(train))
    for fit, held in GroupKFold(folds).split(sa, actions, groups):
        oof[held] = make().fit(sa[fit], actions[fit]).proba(sa[held])
    if calibration == "always":
        cal = IsotonicRegression(out_of_bounds="clip", y_min=1e-6, y_max=1 - 1e-6).fit(oof, actions)
        return cal.predict(raw_p), True
    days = sorted({r["game_id"][:8] for r in train}); cut = days[max(1, int(len(days) * .8)) - 1]
    fit_mask = np.array([r["game_id"][:8] <= cut for r in train]); held_mask = ~fit_mask
    applied = False
    if held_mask.any() and len(set(actions[fit_mask])) == 2:
        cal = IsotonicRegression(out_of_bounds="clip", y_min=1e-6, y_max=1 - 1e-6).fit(oof[fit_mask], actions[fit_mask])
        corrected = cal.predict(oof[held_mask]); truth = actions[held_mask]
        applied = (log_loss(truth, corrected, labels=[0, 1]) < log_loss(truth, oof[held_mask], labels=[0, 1])
                   and brier_score_loss(truth, corrected) <= brier_score_loss(truth, oof[held_mask]))
        if applied:
            cal.fit(oof, actions); p = cal.predict(raw_p)
    return p, applied


def is_called_strike(r):
    return str(r.get("pitch_call_code") or "").upper() == "T" or r.get("event") == "CalledStrike"


def pzone_fit_predict(train, test, fields, seeds=(RS,), es="auto"):
    """old.predict_pzone()과 같은 절차."""
    take = [r for r in train if r["decision_type"] == "Take"]
    y = np.array([is_called_strike(r) for r in take], dtype=int)
    model = Ensemble(old._classifier, seeds, es).fit(old._encode_numeric(take, fields), y)
    return np.clip(model.proba(old._encode_numeric(test, fields)), 1e-6, 1 - 1e-6)


def crossfit(rows, fields, pswing=True, seeds=(RS,), es="auto", drop_game=None, pswing_es=None, calibration="gate"):
    """3블록 교차적합. drop_game이면 그 경기를 데이터에서 뺀다(블록 경계는 날짜 기준이라 그대로).

    es는 p_zone(과 pswing_es가 없으면 p_swing)의 조기 종료, pswing_es는 p_swing만의 조기 종료다.
    """
    pswing_es = es if pswing_es is None else pswing_es
    if drop_game:
        rows = [r for r in rows if r["game_id"] != drop_game]
    ordered, fold, blocks = ordered_folds(rows)
    p_swing = np.full(len(ordered), np.nan); p_zone = np.empty(len(ordered)); applied = []
    t0 = time.time()
    start = 0
    for f, held in enumerate(blocks):
        train = [r for r in rows if r["game_id"][:8] not in held]
        test = ordered[start:start + int((fold == f).sum())]
        sl = slice(start, start + len(test)); start += len(test)
        if pswing:
            p_swing[sl], a = pswing_fit_predict(train, test, seeds, pswing_es, calibration); applied.append(bool(a))
        p_zone[sl] = pzone_fit_predict(train, test, fields, seeds, es)
    return {"rows": ordered, "fold": fold, "p_swing": p_swing, "p_zone": p_zone,
            "calibration_applied": applied, "seconds": time.time() - t0}


def frame(result, p_swing=None):
    """선수·블록 집계용 최소 표."""
    import pandas as pd
    rows = result["rows"]
    df = pd.DataFrame({
        "game_id": [r["game_id"] for r in rows], "batter_id": [str(r["batter_id"]) for r in rows],
        "swing": np.array([r["decision_type"] == "Swing" for r in rows], dtype=int),
        "take_cs": np.array([is_called_strike(r) for r in rows], dtype=int),
        "balls": [r["balls_before"] for r in rows], "strikes": [r["strikes_before"] for r in rows],
        "fold": result["fold"], "p_zone": result["p_zone"],
        "p_swing": result["p_swing"] if p_swing is None else p_swing,
    })
    df["judgment"] = (df.swing - df.p_swing) * (2 * df.p_zone - 1)
    return df


def player_sbj(df, min_n=300):
    g = df.groupby("batter_id")
    n = g.size(); s = 100 * g.judgment.mean()
    return s[n >= min_n]


def block_reproducibility(df):
    out = []
    for a, b in ((0, 1), (1, 2), (0, 2)):
        ga, gb = df[df.fold == a].groupby("batter_id"), df[df.fold == b].groupby("batter_id")
        na, nb = ga.size(), gb.size()
        ids = na.index[na >= 150].intersection(nb.index[nb >= 150])
        out.append(float(np.corrcoef(100 * ga.judgment.mean()[ids], 100 * gb.judgment.mean()[ids])[0, 1]))
    return out


def cluster_z(loss_a, loss_b, games):
    """(b − a) 투구별 손실 차이의 경기 군집 z. 음수면 b가 낮다."""
    import pandas as pd
    d = pd.Series(np.asarray(loss_b) - np.asarray(loss_a))
    n = len(d); m = d.mean()
    g = (d - m).groupby(np.asarray(games)).sum()
    G = len(g); se = np.sqrt(G / (G - 1) * (g ** 2).sum()) / n
    return float(m), float(m / se)


def bernoulli_loss(y, p):
    p = np.clip(p, 1e-15, 1 - 1e-15)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))
