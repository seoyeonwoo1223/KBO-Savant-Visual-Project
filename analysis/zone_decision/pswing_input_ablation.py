"""pSwing 입력 비교 실험 (SBJ/ZA의 p_swing만 대상, p_zone과 DV 모델은 그대로).

현재 코드의 `zone_decision.load_rows()`와 같은 하이퍼파라미터·같은 3개 날짜 블록·같은
isotonic 보정 게이트로 후보마다 p_swing을 다시 적합한다. 후보는 이름으로 고른다.

    PYTHONPATH=src OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
      python analysis/zone_decision/pswing_input_ablation.py --season 2026 --out /tmp/pswing

출력: <out>/pitches_<season>.parquet (후보별 날짜 블록 OOF p·타자 hold-out p),
      <out>/meta_<season>.json (보정 적용 여부, 특성의 구장 편향 진단).
요약은 pswing_input_report.py가 만든다. 재추정 HB/IVB는 SBJ 내부 후보일 뿐이며
Pitch Arsenal 화면 값·보정표·원본 궤적은 읽기만 한다.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.model_selection import GroupKFold

from visualbaseball import plate_decision_v1 as old
from visualbaseball import zone_decision as zd
from visualbaseball.curated import _at_plane
from visualbaseball.pitch_arsenal import PARK_FACTOR_CODE, _pitch_code, _stadium

BASE = old.BASE_NUMERIC
CURRENT_MOVE = ("adjusted_hb_cm", "adjusted_ivb_cm")
REEST_MOVE = ("reest_hb_cm", "reest_ivb_cm")
CAT = old.CATEGORICAL                      # pitch_type, batter_stance, stadium
HAND = ("pitcher_throws",)
PLATOON = ("platoon",)
MOVES = {"none": (), "current": CURRENT_MOVE, "reest": REEST_MOVE}
TRAJ = {"": (), "rel": ("release_x_55",), "ang": ("vaa_deg", "haa_deg"), "both": ("release_x_55", "vaa_deg", "haa_deg")}


def spec(hand: str, move: str, traj: str = "") -> tuple[tuple[str, ...], tuple[str, ...]]:
    cats = CAT + {"": (), "h": HAND, "hp": HAND + PLATOON}[hand]
    return BASE + MOVES[move] + TRAJ[traj], cats


CANDIDATES = {
    "C0": spec("", "current"),           # 현행 운영 입력
    "H1": spec("h", "current"),          # + 투수 손
    "H2": spec("hp", "current"),         # + 투수 손 + 같은 손/반대 손
    "M0": spec("", "none"), "M2": spec("", "reest"),
    "H2M0": spec("hp", "none"), "H2M2": spec("hp", "reest"),
    **{f"H2{m}T{t}": spec("hp", mv, t) for m, mv in (("M0", "none"), ("M1", "current"), ("M2", "reest")) for t in ("rel", "ang", "both")},
}


def classifier(n_numeric: int, n_categorical: int) -> HistGradientBoostingClassifier:
    # old._classifier()와 같은 설정; 범주 수만 후보에 맞춘다.
    return HistGradientBoostingClassifier(
        learning_rate=0.07, max_iter=130, max_leaf_nodes=20, min_samples_leaf=80, l2_regularization=1.5,
        random_state=old.RANDOM_STATE, categorical_features=list(range(n_numeric, n_numeric + n_categorical)))


def encode(train, test, numeric, categorical):
    # zone_decision.encode()와 같은 규칙: 학습에 없던 범주는 결측.
    a = [np.array([old._safe_float(r.get(f)) for r in train]) for f in numeric]
    b = [np.array([old._safe_float(r.get(f)) for r in test]) for f in numeric]
    for f in categorical:
        mapping = {v: i for i, v in enumerate(sorted({str(r.get(f) or "") for r in train}))}
        a.append(np.array([mapping[str(r.get(f) or "")] for r in train], dtype=float))
        b.append(np.array([mapping.get(str(r.get(f) or ""), np.nan) for r in test], dtype=float))
    return np.column_stack(a), np.column_stack(b)


def propensity(train, test, numeric, categorical, calibration=True):
    """zone_decision.fit_predict()의 p_swing 부분을 그대로 옮긴 것."""
    a, b = encode(train, test, numeric, categorical)
    y = np.array([r["decision_type"] == "Swing" for r in train], dtype=int)
    model = zd.fit_model(classifier(len(numeric), len(categorical)), a, y)
    raw = model.predict_proba(b)[:, list(model.classes_).index(1)]
    p, applied = raw.copy(), False
    if calibration:
        groups = np.array([r["game_id"] for r in train])
        oof = np.empty(len(train))
        for fit, held in GroupKFold(min(3, len(set(groups)))).split(a, y, groups):
            m = zd.fit_model(classifier(len(numeric), len(categorical)), a[fit], y[fit])
            oof[held] = m.predict_proba(a[held])[:, list(m.classes_).index(1)]
        days = sorted({r["game_id"][:8] for r in train}); cut = days[max(1, int(len(days) * .8)) - 1]
        fit_mask = np.array([r["game_id"][:8] <= cut for r in train]); held_mask = ~fit_mask
        if held_mask.any() and len(set(y[fit_mask])) == 2:
            cal = IsotonicRegression(out_of_bounds="clip", y_min=1e-6, y_max=1 - 1e-6).fit(oof[fit_mask], y[fit_mask])
            corrected = cal.predict(oof[held_mask]); truth = y[held_mask]
            applied = bool(log_loss(truth, corrected, labels=[0, 1]) < log_loss(truth, oof[held_mask], labels=[0, 1])
                           and brier_score_loss(truth, corrected) <= brier_score_loss(truth, oof[held_mask]))
            if applied:
                cal.fit(oof, y); p = cal.predict(raw)
    return p, raw, applied


def park_code(r):
    return PARK_FACTOR_CODE.get(_pitch_code(r), _pitch_code(r))


def two_way_park_effect(rows, value):
    """value = (투수, 구종) 효과 + (구장, 구종) 효과. 구장 효과는 구종 안에서 투구 가중 평균 0."""
    keep = [r for r in rows if np.isfinite(old._safe_float(r.get(value))) and park_code(r) and r.get("pitcher_id")]
    y = np.array([float(r[value]) for r in keep])
    a = pd.factorize(pd.Series([f"{r['pitcher_id']}|{park_code(r)}" for r in keep]))[0]
    keys = pd.Series([(_stadium(r.get("stadium")), park_code(r)) for r in keep])
    b, levels = pd.factorize(keys)
    ea, eb = np.zeros(a.max() + 1), np.zeros(b.max() + 1)
    na, nb = np.bincount(a), np.bincount(b)
    for _ in range(100):
        ea = np.bincount(a, y - eb[b]) / na
        eb = np.bincount(b, y - ea[a]) / nb
    effect = pd.DataFrame({"park": [k[0] for k in levels], "code": [k[1] for k in levels], "eff": eb, "n": nb})
    weighted = (effect.eff * effect.n).groupby(effect.code).transform("sum") / effect.n.groupby(effect.code).transform("sum")
    effect["eff"] -= weighted
    resid_sd = float(np.std(y - ea[a] - eb[b]))
    return effect, resid_sd


def add_reestimated_movement(train, test):
    """훈련 블록의 원시 VB 무브먼트만으로 구장×구종 오프셋을 다시 추정해 SBJ 내부 후보로만 쓴다."""
    offsets = {}
    for raw, out in (("horizontal_movement_cm", "reest_hb_cm"), ("vertical_movement_cm", "reest_ivb_cm")):
        effect, _ = two_way_park_effect(train, raw)
        offsets[out] = {(p, c): -e for p, c, e, n in effect[["park", "code", "eff", "n"]].itertuples(index=False) if n >= 300}
    for rows in (train, test):
        for r in rows:
            key = (_stadium(r.get("stadium")), park_code(r))
            for raw, out in (("horizontal_movement_cm", "reest_hb_cm"), ("vertical_movement_cm", "reest_ivb_cm")):
                v, off = old._safe_float(r.get(raw)), offsets[out].get(key)
                r[out] = v + off if off is not None and np.isfinite(v) else np.nan


def add_trajectory(rows):
    # 접근각은 앞면(y=17/12 ft)의 속도 방향. 투구 전체의 궤적 요약이지 결정 이후 결과가 아니다.
    for r in rows:
        at = _at_plane(r, 17 / 12) if r.get("trajectory_valid") else None
        if at is None:
            r["vaa_deg"] = r["haa_deg"] = np.nan
        else:
            _, _, vx, vy, vz = at
            r["vaa_deg"] = math.degrees(math.atan2(vz, -vy)); r["haa_deg"] = math.degrees(math.atan2(vx, -vy))


def load(root: Path, season: int):
    extra = ("pitcher_id", "pitch_type_code", "pitch_type_kr", "horizontal_movement_cm", "vertical_movement_cm", "release_x_50",
             "release_x_55", "trajectory_valid", "x0", "y0", "z0", "vx0", "vy0", "vz0", "ax", "ay", "az")
    saved = zd.NUMERIC
    zd.NUMERIC = saved + extra          # load_rows()의 keep 목록만 넓힌다. 행 선택·보정은 운영과 동일.
    try:
        rows, source = zd.load_rows(root, season)
    finally:
        zd.NUMERIC = saved
    bio = {r["player_id"]: r["throws"] for r in pq.read_table(root / "data/curated/players/player_bio.parquet", columns=["player_id", "throws"]).to_pylist()}
    for r in rows:
        hand = bio.get(str(r.get("pitcher_id") or ""))
        if hand not in ("R", "L"):
            x = old._safe_float(r.get("release_x_50"))
            hand = ("L" if x > 0 else "R") if np.isfinite(x) and abs(x) >= 0.1 else ""
        r["pitcher_throws"] = hand
        stance = r.get("batter_stance") or ""
        r["platoon"] = ("same" if stance == hand else "opposite") if stance and hand else ""
    add_trajectory(rows)
    return rows, source


def feature_park_bias(rows):
    out = {}
    for f in ("horizontal_movement_cm", "adjusted_hb_cm", "vertical_movement_cm", "adjusted_ivb_cm", "release_x_55", "vaa_deg", "haa_deg"):
        effect, resid = two_way_park_effect(rows, f)
        e = effect[effect.n >= 300]
        per_park = (e.eff * e.n).groupby(e.park).sum() / e.n.groupby(e.park).sum()
        out[f] = {"park_range": float(per_park.max() - per_park.min()), "max_abs_park_type": float(e.eff.abs().max()),
                  "within_pitcher_type_sd": resid, "range_over_sd": float((per_park.max() - per_park.min()) / resid)}
    return out


def run(root: Path, season: int, names: list[str], out: Path):
    t0 = time.time()
    rows, source = load(root, season)
    print(season, "rows", len(rows), f"{time.time() - t0:.0f}s", flush=True)
    meta = {"season": season, "rows": len(rows), "candidates": {n: {"numeric": list(CANDIDATES[n][0]), "categorical": list(CANDIDATES[n][1])} for n in names},
            "movement_source": source["movement"], "calibration_applied": {}, "feature_park_bias": feature_park_bias(rows)}
    dates = np.array(sorted({r["game_id"][:8] for r in rows}))
    blocks = np.array_split(dates, zd.CROSSFIT_FOLDS)
    frame = pd.DataFrame({k: [r.get(k) for r in rows] for k in ("game_id", "batter_id", "batter_name", "stadium", "pitch_type", "batter_stance", "pitcher_throws", "platoon", "region")})
    frame["swing"] = [int(r["decision_type"] == "Swing") for r in rows]
    frame["fold"] = -1; frame["p_zone"] = np.nan
    for n in names:
        frame[f"p_{n}"] = np.nan; frame[f"raw_{n}"] = np.nan; frame[f"bh_{n}"] = np.nan
        meta["calibration_applied"][n] = []
    index = {id(r): i for i, r in enumerate(rows)}
    for fold, block in enumerate(blocks):
        held = set(block)
        train = [r for r in rows if r["game_id"][:8] not in held]; test = [r for r in rows if r["game_id"][:8] in held]
        ids = np.array([index[id(r)] for r in test])
        add_reestimated_movement(train, test)
        frame.loc[ids, "fold"] = fold
        frame.loc[ids, "p_zone"] = old.predict_pzone(train, test, zd.pzone_fields(season))
        for n in names:
            p, raw, applied = propensity(train, test, *CANDIDATES[n])
            frame.loc[ids, f"p_{n}"] = p; frame.loc[ids, f"raw_{n}"] = raw
            meta["calibration_applied"][n].append(applied)
            print(f"  {season} block {fold + 1} {n} {time.time() - t0:.0f}s", flush=True)
    # 타자 단위 hold-out: 같은 타자의 투구가 학습에 전혀 없는 조건 (날짜는 섞임, 보정 없음).
    batters = np.array([str(r["batter_id"]) for r in rows])
    for fold, (tr, te) in enumerate(GroupKFold(3).split(np.zeros(len(rows)), groups=batters)):
        train = [rows[i] for i in tr]; test = [rows[i] for i in te]
        add_reestimated_movement(train, test)
        for n in names:
            _, raw, _ = propensity(train, test, *CANDIDATES[n], calibration=False)
            frame.loc[te, f"bh_{n}"] = raw
        print(f"  {season} batter fold {fold + 1} {time.time() - t0:.0f}s", flush=True)
    out.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out / f"pitches_{season}.parquet", index=False)
    (out / f"meta_{season}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--candidates", nargs="+", default=list(CANDIDATES))
    args = parser.parse_args()
    run(Path(args.root).resolve(), args.season, args.candidates, Path(args.out))
