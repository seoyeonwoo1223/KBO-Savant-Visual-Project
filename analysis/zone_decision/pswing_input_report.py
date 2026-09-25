"""pswing_input_ablation.py 출력의 비교표. 채택 규칙은 결과를 보기 전에 고정했다.

    python analysis/zone_decision/pswing_input_report.py --out /tmp/pswing

특성 묶음 X를 비교 기준 B(X만 없는 모델)에 더해 채택하려면 세 시즌 모두에서
  1. 날짜 블록 OOF log loss가 경기 군집 paired SE의 2배보다 크게 낮아지고,
  2. 타자 hold-out log loss도 같은 기준으로 낮아지며,
  3. 보정 오차(ECE, 20 분위 구간)가 0.001보다 크게 나빠지지 않고,
  4. 구장×구종 셀 잔차의 가중 RMS가 5%보다 크게 나빠지지 않아야 한다.
선수 SBJ 변화(순위 상관, 최대 변화, 구장별 평균 판단 변화)와 분할 반쪽 신뢰도는
채택 조건이 아니라, 위 조건을 통과한 후보가 무엇을 바꾸는지 보이는 진단이다.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

SEASONS = (2024, 2025, 2026)
COMPARISONS = [  # (이름, 후보, 비교 기준)
    ("투수 손", "H1", "C0"),
    ("같은 손/반대 손 상호작용", "H2", "H1"),
    ("투수 손+상호작용", "H2", "C0"),
    ("현행 보정 무브먼트 (손 없음)", "C0", "M0"),
    ("재추정 보정 무브먼트 (손 없음)", "M2", "M0"),
    ("현행 보정 무브먼트", "H2", "H2M0"),
    ("재추정 보정 무브먼트", "H2M2", "H2M0"),
    ("재추정 vs 현행 보정", "H2M2", "H2"),
    *[(f"궤적 {t} (무브먼트 {m})", f"H2{mk}T{t}", base)
      for t in ("rel", "ang", "both") for m, mk, base in (("제외", "M0", "H2M0"), ("현행", "M1", "H2"), ("재추정", "M2", "H2M2"))],
    *[(f"궤적 {t} 대신 현행 무브먼트", "H2", f"H2M0T{t}") for t in ("rel", "ang", "both")],
    # 2차: 채택된 투수 손(H1) 기반의 최종 비교
    ("[H1] 현행 보정 무브먼트", "H1", "H1M0"),
    ("[H1] 재추정(구종) 무브먼트", "H1M2", "H1M0"),
    ("[H1] 재추정(구종×손) 무브먼트", "H1M3", "H1M0"),
    ("[H1] 재추정(구종×손) vs 현행", "H1M3", "H1"),
    ("[H1] 릴리스 좌우 (무브먼트 제외)", "H1M0Trel", "H1M0"),
    ("[H1] 릴리스 좌우 대신 현행 무브먼트", "H1", "H1M0Trel"),
]


def clip(p):
    return np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)


def pitch_ll(y, p):
    p = clip(p)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def clustered_mean_se(values, groups):
    frame = pd.DataFrame({"v": values, "g": groups})
    sums = frame.groupby("g").v.agg(["sum", "size"])
    total, n, g = sums["sum"].sum(), sums["size"].sum(), len(sums)
    mean = total / n
    se = np.sqrt(g / (g - 1) * ((sums["sum"] - mean * sums["size"]) ** 2).sum()) / n
    return float(mean), float(se)


def ece(y, p, bins=20):
    order = np.argsort(p, kind="stable")
    return float(sum(abs(y[idx].mean() - p[idx].mean()) * len(idx) for idx in np.array_split(order, bins)) / len(y))


def calibration_slope(y, p):
    x = np.log(clip(p) / (1 - clip(p))); X = np.c_[np.ones_like(x), x]; b = np.array([0.0, 1.0])
    for _ in range(25):
        q = 1 / (1 + np.exp(-X @ b)); w = q * (1 - q)
        b += np.linalg.solve(X.T @ (X * w[:, None]), X.T @ (y - q))
    return float(b[1])


def cell_residuals(frame, col):
    y, p = frame.swing.to_numpy(float), clip(frame[col])
    g = pd.DataFrame({"s": frame.stadium, "t": frame.pitch_type, "r": y - p, "v": p * (1 - p)}).groupby(["s", "t"]).agg(n=("r", "size"), r=("r", "sum"), v=("v", "sum"))
    g = g[g.n >= 300]
    mean = g.r / g.n
    return {"rms_pp": float(100 * np.sqrt(np.average(mean ** 2, weights=g.n))), "cells": int(len(g)),
            "cells_abs_z_gt_3": int((np.abs(g.r / np.sqrt(g.v)) > 3).sum()),
            # 보조(사후 추가): 셀 z²의 평균. 표본 잡음만 있으면 약 1이다. RMS는 잡음을 포함한다.
            "mean_z2": float(np.mean(g.r ** 2 / g.v))}


def za(frame, col):
    j = 100 * (frame.swing - clip(frame[col])) * (2 * frame.p_zone - 1)
    return j


def player_scores(frame, col, minimum=300):
    j = za(frame, col)
    g = pd.DataFrame({"b": frame.batter_id, "j": j}).groupby("b").j.agg(["mean", "size"])
    return g[g["size"] >= minimum]["mean"]


def split_half(frame, col, minimum=150):
    games = sorted(frame.game_id.unique()); half = frame.game_id.map({g: i % 2 for i, g in enumerate(games)})
    j = za(frame, col)
    parts = [pd.DataFrame({"b": frame.batter_id[half == h], "j": j[half == h]}).groupby("b").j.agg(["mean", "size"]) for h in (0, 1)]
    both = parts[0].join(parts[1], lsuffix="0", rsuffix="1")
    both = both[(both.size0 >= minimum) & (both.size1 >= minimum)]
    r = float(np.corrcoef(both.mean0, both.mean1)[0, 1])
    return {"batters": int(len(both)), "r": r, "spearman_brown": 2 * r / (1 + r)}


def model_summary(frame, name):
    y = frame.swing.to_numpy(float)
    return {"oof_logloss": float(pitch_ll(y, frame[f"p_{name}"]).mean()), "oof_brier": float(np.mean((frame[f"p_{name}"] - y) ** 2)),
            "oof_ece": ece(y, clip(frame[f"p_{name}"])), "oof_slope": calibration_slope(y, frame[f"p_{name}"]),
            "batter_holdout_logloss": float(pitch_ll(y, frame[f"bh_{name}"]).mean()),
            "batter_holdout_ece": ece(y, clip(frame[f"bh_{name}"])),
            "park_type": cell_residuals(frame, f"p_{name}"), "split_half": split_half(frame, f"p_{name}")}


def compare(frame, new, base, summary):
    y = frame.swing.to_numpy(float)
    out = {}
    for kind, prefix in (("oof", "p_"), ("batter_holdout", "bh_"), ("oof_raw", "raw_")):
        diff = pitch_ll(y, frame[prefix + new]) - pitch_ll(y, frame[prefix + base])
        mean, se = clustered_mean_se(diff, frame.game_id.to_numpy())
        out[kind] = {"delta": mean, "se": se, "z": mean / se if se else 0.0}
    out["ece_delta"] = summary[new]["oof_ece"] - summary[base]["oof_ece"]
    out["park_rms_ratio"] = summary[new]["park_type"]["rms_pp"] / summary[base]["park_type"]["rms_pp"]
    out["park_mean_z2"] = [summary[base]["park_type"]["mean_z2"], summary[new]["park_type"]["mean_z2"]]
    out["passes"] = bool(out["oof"]["z"] < -2 and out["batter_holdout"]["z"] < -2 and out["ece_delta"] <= 0.001 and out["park_rms_ratio"] <= 1.05)
    a, b = player_scores(frame, f"p_{base}"), player_scores(frame, f"p_{new}")
    delta = (b - a).dropna()
    ra, rb = a.rank(ascending=False), b.rank(ascending=False)
    top_a, top_b = set(a.nlargest(20).index), set(b.nlargest(20).index)
    dj = za(frame, f"p_{new}") - za(frame, f"p_{base}")
    park = dj.groupby(frame.stadium).mean()
    park = park[frame.stadium.value_counts().reindex(park.index) >= 3000]
    out["players"] = {"qualified": int(len(delta)), "spearman": float(spearmanr(a, b.reindex(a.index)).statistic),
                      "mean_abs_delta": float(delta.abs().mean()), "max_abs_delta": float(delta.abs().max()),
                      "max_rank_change": int((ra - rb.reindex(ra.index)).abs().max()), "top20_changed": len(top_a - top_b),
                      "stadium_mean_judgment_range": float(park.max() - park.min())}
    return out


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--out", required=True); args = parser.parse_args()
    out = Path(args.out); result = {}
    for season in SEASONS:
        frame = pd.read_parquet(out / f"pitches_{season}.parquet")
        meta = json.loads((out / f"meta_{season}.json").read_text(encoding="utf-8"))
        names = [c[4:] for c in frame.columns if c.startswith("raw_")]
        summary = {n: model_summary(frame, n) for n in names}
        comps = {label: compare(frame, new, base, summary) for label, new, base in COMPARISONS if new in names and base in names}
        result[season] = {"models": summary, "comparisons": comps, "calibration_applied": meta["calibration_applied"],
                          "feature_park_bias": meta["feature_park_bias"]}
    (out / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print("## 모델별 (시즌: OOF logloss / ECE / 기울기 / 타자 hold-out logloss / 구장×구종 RMS pp·|z|>3 셀 / 분할 반쪽 r)")
    for name in result[SEASONS[0]]["models"]:
        cells = []
        for s in SEASONS:
            m = result[s]["models"][name]
            cells.append(f"{m['oof_logloss']:.5f} / {m['oof_ece']:.4f} / {m['oof_slope']:.3f} / {m['batter_holdout_logloss']:.5f} / "
                         f"{m['park_type']['rms_pp']:.2f}·{m['park_type']['cells_abs_z_gt_3']} / {m['split_half']['r']:.3f}")
        print(f"| {name} | " + " | ".join(cells) + " |")
    print("\n## 비교 (시즌별: ΔOOF(z) / Δ타자hold-out(z) / ΔECE / 구장 RMS 비 / 통과 | 선수: ρ, 평균|Δ|, 최대|Δ|, 최대 순위 변화, top20 교체, 구장별 판단 변화 범위)")
    for label, *_ in COMPARISONS:
        if label not in result[SEASONS[0]]["comparisons"]:
            continue
        cells = []
        for s in SEASONS:
            c = result[s]["comparisons"][label]; p = c["players"]
            cells.append(f"{c['oof']['delta']:+.5f}({c['oof']['z']:+.1f}) / {c['batter_holdout']['delta']:+.5f}({c['batter_holdout']['z']:+.1f}) / "
                         f"{c['ece_delta']:+.4f} / {c['park_rms_ratio']:.3f} / {'O' if c['passes'] else 'X'} | "
                         f"{p['spearman']:.4f}, {p['mean_abs_delta']:.3f}, {p['max_abs_delta']:.3f}, {p['max_rank_change']}, {p['top20_changed']}, {p['stadium_mean_judgment_range']:.3f}")
        print(f"| {label} | " + " | ".join(cells) + " |")
    print("\n## 보조 진단 (사후 추가, 채택 규칙 밖): 보정 전 OOF Δlogloss(z) / 구장×구종 셀 평균 z² (기준→후보)")
    for label, *_ in COMPARISONS:
        if label in result[SEASONS[0]]["comparisons"]:
            print(f"| {label} | " + " | ".join(f"{c['oof_raw']['delta']:+.5f}({c['oof_raw']['z']:+.1f}) / {c['park_mean_z2'][0]:.2f}→{c['park_mean_z2'][1]:.2f}" for c in (result[s]["comparisons"][label] for s in SEASONS)) + " |")
    print("\n## 특성의 구장 편향 (투수×구종 + 구장×구종 고정효과; 구장 효과 범위 / 투수×구종 내 SD)")
    for f in result[SEASONS[0]]["feature_park_bias"]:
        print(f"| {f} | " + " | ".join(f"{result[s]['feature_park_bias'][f]['park_range']:.2f} / {result[s]['feature_park_bias'][f]['within_pitcher_type_sd']:.2f} ({result[s]['feature_park_bias'][f]['range_over_sd']:.2f})" for s in SEASONS) + " |")


if __name__ == "__main__":
    main()
