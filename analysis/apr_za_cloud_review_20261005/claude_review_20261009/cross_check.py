"""협업 창구 0012: 0011(B1 조건부 SE·공식 신장·ABS 끝면) 독립 교차검산. 모형을 적합하지 않으며 새 실험이 아니다.

1. B1 합성: gates.md B1 등록 문안만 보고 생성기·추정기를 다시 구현하고 다른 seed로 108셀을 재현한다.
   참 공분산·경기 내 상관과 평균 공동 추정의 해석적 편향을 대조한다.
2. B1 관측: 선수별 경기 bootstrap을 가중 행 복제로 독립 구현해 gpt bootstrap SE와 비교하고,
   RB3 문턱이 현행 SE와 IF SE를 구별할 수 있는지 본다.
3. 실제 자료 특성: 경기당 투구 수, 경기 내 상관, 경기 합 U의 첨도를 합성 격자와 나란히 둔다. 포함률은 계산하지 않는다.
4. 신장: KBO 프로필 신장(gpt 스냅샷)과 VB ABS 존을 공식 비율로 역산한 신장을 대조하고, 시즌별 포함률을 낸다.
5. ABS 끝면 1.5cm: 현행 top/bottom gap과 공식 기하의 차이. 입력 기하만 보며 콜·모형은 쓰지 않는다.

실행 (저장소 루트): PYTHONPATH=src OMP_NUM_THREADS=2 python analysis/apr_za_cloud_review_20261005/claude_review_20261009/cross_check.py
"""
from __future__ import annotations

import hashlib
import io
import itertools
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.stats import kurtosis, t as student_t

from visualbaseball.curated import load_table

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
GPT = HERE.parent / "gpt_review_20261009"
sys.path.insert(0, str(GPT))
from run_b1 import bootstrap_stats as gpt_bootstrap_stats  # noqa: E402  대조 전용. 위 재구현은 이 함수를 쓰지 않는다
SOURCE = "e48da3a26a617db67fbb51f6b1cbcb072b729eaf"
PITCHES = "data/metrics/zone_awareness/2026/pitches.parquet"
PITCH_SHA = "f754f18cc972775315be87eabd4fc88b3c873c420f8e439c0fea5ad13acdfe5f"
SEED = 20261012  # gpt seed(20261005)와 다르게 둔다
REPS, BOOT = 2000, 2000
Z975 = 1.959963984540054
CM = 30.48
# 공식 신장 비율 (gpt_review_20261009/abs_geometry_review.json, kbo_abs_2026_supplement.json; 2026 그림 직접 확인)
ABS_RATIO = {2024: (.5635, .2764), 2025: (.5575, .2704), 2026: (.5575, .2704)}
BACK_OFFSET_CM = 1.5


def q(x, ps=(.05, .5, .95)) -> list[float]:
    return [float(v) for v in np.quantile(np.asarray(x, float), ps)]


# 1. B1 합성 ---------------------------------------------------------------

def game_sizes(n: int, unequal: bool) -> np.ndarray:
    games = n // 10
    if not unequal:
        return np.full(games, 10)
    w = np.array([i % 3 + 1 for i in range(games)], float)
    m = np.floor(n * w / w.sum()).astype(int)
    m[: n - m.sum()] += 1
    return m


def draw(family: str, n: int, h: float, c: float, m: np.ndarray, rng) -> tuple[np.ndarray, np.ndarray, float]:
    gi = np.repeat(np.arange(len(m)), m)
    if family == "gaussian":
        # 경기효과 (a, b)와 투구효과 (e, f): 각각 분산 1, 상관 c인 이변량 정규
        chol = np.linalg.cholesky(np.array([[1, c], [c, 1]]))
        ga = rng.standard_normal((REPS, len(m), 2)) @ chol.T
        pe = rng.standard_normal((REPS, n, 2)) @ chol.T
        r = .1 + np.sqrt(h) * ga[:, gi, 0] + np.sqrt(1 - h) * pe[..., 0]
        d = .2 + np.sqrt(h) * ga[:, gi, 1] + np.sqrt(1 - h) * pe[..., 1]
        return r, d, 200 * c
    shared = np.where(rng.random((REPS, len(m))) < .5, -1., 1.)
    own = np.where(rng.random((REPS, n)) < .5, -1., 1.)
    x = np.where(rng.random((REPS, n)) < np.sqrt(h), shared[:, gi], own)
    s, p = (x + 1) / 2, .5
    zg, zt = rng.standard_normal((REPS, len(m))), rng.standard_normal((REPS, n))
    d = .2 + c * x + np.sqrt(1 - c * c) * (np.sqrt(h) * zg[:, gi] + np.sqrt(1 - h) * zt)
    return s - p, d, 100 * c


def cluster_if(r: np.ndarray, d: np.ndarray, m: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n, games = r.shape[-1], len(m)
    rc, dc = r - r.mean(-1, keepdims=True), d - d.mean(-1, keepdims=True)
    cov = (rc * dc).mean(-1)
    member = np.zeros((n, games))
    member[np.arange(n), np.repeat(np.arange(games), m)] = 1
    u = (200 * (rc * dc - cov[..., None])) @ member
    se = np.sqrt(games / (games - 1) * (u * u).sum(-1)) / n
    return 200 * cov, se, u


def synthetic() -> dict:
    gpt = pd.read_csv(GPT / "b1_simulation.csv")
    rows, truth_moments = [], []
    grid = itertools.product(["gaussian", "binary"], [100, 300, 1000], [0, .1, .3], [-.3, 0, .3], ["equal", "unequal"])
    for cell, (fam, n, h, c, shape) in enumerate(grid):
        rng = np.random.default_rng([SEED, cell])
        m = game_sizes(n, shape == "unequal")
        r, d, truth = draw(fam, n, h, c, m, rng)
        b, se, u = cluster_if(r, d, m)
        games = len(m)
        # 평균 공동 추정의 해석적 기대값: E[B̂] = B·(1 − (1 + h(Σm²/n − 1))/n)
        expected = truth * (1 - (1 + h * ((m * m).sum() / n - 1)) / n)
        cover = float(np.mean(np.abs(b - truth) <= Z975 * se))
        g = gpt.iloc[cell]
        assert (g.family, g.n, g.icc, g.association, g.size_design) == (fam, n, h, c, shape)
        uz = u / np.sqrt((u * u).mean(-1, keepdims=True))
        rows.append({
            "cell": cell, "family": fam, "n": n, "G": games, "icc": h, "association": c, "size_design": shape,
            "true_B": truth, "expected_B_analytic": expected, "mean_B": float(b.mean()),
            "bias_vs_analytic_z": float((b.mean() - expected) / (b.std(ddof=1) / np.sqrt(REPS))) if b.std() > 0 else 0.,
            "sd_B": float(b.std(ddof=1)), "mean_se": float(se.mean()), "coverage": cover,
            "coverage_t": float(np.mean(np.abs(b - truth) <= student_t.ppf(.975, games - 1) * se)),
            "gpt_coverage": float(g.coverage), "gpt_coverage_t": float(g.coverage_t_diagnostic),
            "coverage_diff_z": float((cover - g.coverage) / np.sqrt(max(cover * (1 - cover), 1e-12) * 2 / REPS)),
            "u_excess_kurtosis": float(np.mean(kurtosis(uz, axis=-1))),
        })
        if n == 1000 and shape == "equal":
            # 참 모멘트: 같은 경기의 서로 다른 투구 쌍과 같은 투구
            rr, dd = r[:200] - r[:200].mean(), d[:200] - d[:200].mean()
            first, second = np.cumsum(m) - m, np.cumsum(m) - m + 1
            truth_moments.append({
                "family": fam, "icc": h, "association": c,
                "var_r": float(rr.var()), "var_d": float(dd.var()), "cov_rd": float((rr * dd).mean()),
                "same_game_corr_r": float(np.mean(rr[:, first] * rr[:, second]) / rr.var()),
                "same_game_corr_d": float(np.mean(dd[:, first] * dd[:, second]) / dd.var()),
                "same_game_cross_cov": float(np.mean(rr[:, first] * dd[:, second]))})
    df = pd.DataFrame(rows)
    df.to_csv(HERE / "b1_synthetic_replication.csv", index=False)
    primary, small = df[df.G >= 20], df[df.G < 20]
    return {
        "seed": SEED, "cells": len(df), "primary_cells": int(len(primary)),
        "primary_coverage_range": [float(primary.coverage.min()), float(primary.coverage.max())],
        "primary_cells_outside_92_98": primary[(primary.coverage < .92) | (primary.coverage > .98)].cell.tolist(),
        "mean_coverage_by_G": {str(g): {"claude": float(x.coverage.mean()), "gpt": float(x.gpt_coverage.mean()),
                                        "claude_min": float(x.coverage.min()), "gpt_min": float(x.gpt_coverage.min())}
                               for g, x in df.groupby("G")},
        "coverage_diff_vs_gpt_abs_z_max": float(df.coverage_diff_z.abs().max()),
        "coverage_diff_vs_gpt_abs_z_over_2_576": int((df.coverage_diff_z.abs() > 2.576).sum()),
        "bias_vs_analytic_abs_z_max": float(df.bias_vs_analytic_z.abs().max()),
        "max_abs_relative_analytic_bias_n300plus": float(((df.expected_B_analytic - df.true_B).abs() / df.true_B.abs().replace(0, np.nan))[df.n >= 300].max()),
        "G10_coverage_normal_range": [float(small.coverage.min()), float(small.coverage.max())],
        "G10_coverage_t_range": [float(small.coverage_t.min()), float(small.coverage_t.max())],
        "G10_gpt_coverage_t_range": [float(small.gpt_coverage_t.min()), float(small.gpt_coverage_t.max())],
        "G10_cells_t_inside_92_98": int(((small.coverage_t >= .92) & (small.coverage_t <= .98)).sum()),
        "u_excess_kurtosis_by_family_n1000": {f: q(df[(df.family == f) & (df.n == 1000)].u_excess_kurtosis, (0, .5, 1)) for f in ("gaussian", "binary")},
        "truth_moments_n1000_equal_200reps": truth_moments,
    }


# 2–3. B1 관측 ------------------------------------------------------------

def pitches_2026() -> pd.DataFrame:
    blob = subprocess.check_output(["git", "show", f"{SOURCE}:{PITCHES}"], cwd=ROOT)
    assert hashlib.sha256(blob).hexdigest() == PITCH_SHA
    cols = ["batter_id", "game_id", "swing", "p_swing", "delta_v", "sz_top", "sz_bottom", "top_gap_cm", "bottom_gap_cm", "plane_fallback"]
    df = pq.ParquetFile(io.BytesIO(blob)).read(columns=cols).to_pandas()
    df["batter_id"] = df.batter_id.astype(str)
    return df


def anova_icc(x: np.ndarray, game: np.ndarray) -> float:
    """일원 분산분석 ICC (불균등 경기 크기)."""
    s = pd.DataFrame({"x": x, "g": game}).groupby("g").x
    k, mean, size = s.ngroups, s.mean(), s.size()
    n = len(x)
    msb = (size * (mean - x.mean()) ** 2).sum() / (k - 1)
    msw = ((x - s.transform("mean")) ** 2).sum() / (n - k)
    n0 = (n - (size ** 2).sum() / n) / (k - 1)
    return float((msb - msw) / (msb + (n0 - 1) * msw))


def empirical(df: pd.DataFrame) -> dict:
    gpt = pd.read_csv(GPT / "b1_players_2026.csv", dtype={"batter_id": str}).set_index("batter_id")
    rows = []
    for j, (pid, f) in enumerate(df.groupby("batter_id", sort=True)):
        n, games = len(f), f.game_id.nunique()
        if not (n >= 300 and games >= 20):
            continue
        r, d = (f.swing - f.p_swing).to_numpy(float), f.delta_v.to_numpy(float)
        codes = pd.factorize(f.game_id)[0]
        rc, dc = r - r.mean(), d - d.mean()
        cov = np.mean(rc * dc)
        u = np.bincount(codes, 200 * (rc * dc - cov))
        se_raw = np.sqrt((u * u).sum()) / n
        # 가중 행 복제: 경기 다중도 k를 그 경기 모든 투구의 가중치로 펼친다 (복제 경기는 독립 복제)
        rng = np.random.default_rng([SEED, 7, j])
        k = rng.multinomial(games, np.full(games, 1 / games), size=BOOT)
        w = k[:, codes].astype(float)
        nn = w.sum(1)
        mr, md = (w @ r) / nn, (w @ d) / nn
        boot = 200 * ((w @ (r * d)) / nn - mr * md)
        # 복제별 SE*: 평균·공분산을 복제마다 다시 잡고, 중복 경기는 k배의 독립 군집으로 센다 (앞 50회만 gpt 함수와 대조)
        cov_star = boot[:50] / 200
        psi_star = 200 * ((r - mr[:50, None]) * (d - md[:50, None]) - cov_star[:, None])
        u_star = np.stack([np.bincount(codes, row, minlength=games) for row in psi_star])
        se_star = np.sqrt(games / (games - 1) * (k[:50] * u_star ** 2).sum(1)) / nn[:50]
        agg = pd.DataFrame({"g": codes, "n": 1., "r": r, "d": d, "rd": r * d}).groupby("g")[["n", "r", "d", "rd"]].sum().to_numpy()
        b_gpt, se_gpt = gpt_bootstrap_stats(agg, k[:50])
        g = gpt.loc[pid]
        rows.append({
            "batter_id": pid, "n": n, "G": games, "pitches_per_game": n / games,
            "B": 200 * cov, "B_gpt": float(g.B), "se_if_raw": se_raw, "se_if_g": se_raw * np.sqrt(games / (games - 1)),
            "se_current_gpt": float(g.se_current), "boot_se": float(boot.std(ddof=1)), "boot_se_gpt": float(g.bootstrap_se),
            "boot_star_max_rel_diff_vs_gpt_fn": float(max(np.max(np.abs(b_gpt - boot[:50]) / np.abs(boot[:50]).max()),
                                                          np.max(np.abs(se_gpt - se_star) / se_star))),
            "icc_r": anova_icc(r, codes), "icc_d": anova_icc(d, codes),
            "u_excess_kurtosis": float(kurtosis(u / np.sqrt((u * u).mean()))),
            "psi_excess_kurtosis": float(kurtosis(rc * dc)),
        })
    p = pd.DataFrame(rows)
    p.to_csv(HERE / "b1_empirical_crosscheck.csv", index=False)
    lim = lambda x: bool(.90 <= np.median(x) <= 1.10 and np.quantile(x, .05) >= .75 and np.quantile(x, .95) <= 1.25)
    mc_sd = 1 / np.sqrt(2 * (BOOT - 1))
    return {
        "players": int(len(p)), "B_max_abs_diff_vs_gpt": float((p.B - p.B_gpt).abs().max()),
        "boot_star_B_SE_max_rel_diff_vs_gpt_function_50reps": float(p.boot_star_max_rel_diff_vs_gpt_fn.max()),
        "qualified_G_below_30": int((p.G < 30).sum()), "qualified_G_below_40": int((p.G < 40).sum()),
        "boot_se_claude_over_gpt_p05_p50_p95": q(p.boot_se / p.boot_se_gpt),
        "boot_se_claude_over_gpt_expected_sd_if_normal": float(np.sqrt(2) * mc_sd),
        "if_raw_over_boot_p05_p50_p95": q(p.se_if_raw / p.boot_se),
        "if_raw_over_boot_sd": float((p.se_if_raw / p.boot_se).std(ddof=1)),
        "bootstrap_sd_relative_mc_sd_if_normal": float(mc_sd),
        "if_g_over_boot_p05_p50_p95": q(p.se_if_g / p.boot_se), "RB3_if_g_pass": lim(p.se_if_g / p.boot_se),
        "current_over_boot_p05_p50_p95": q(p.se_current_gpt / p.boot_se), "RB3_current_pass": lim(p.se_current_gpt / p.boot_se),
        "current_over_boot_gpt_p05_p50_p95": q(p.se_current_gpt / p.boot_se_gpt), "RB3_current_pass_gpt_boot": lim(p.se_current_gpt / p.boot_se_gpt),
        "sqrt_G_over_G_minus_1_p50": float(np.median(np.sqrt(p.G / (p.G - 1)))),
        "G_min_p50_max": [int(p.G.min()), float(p.G.median()), int(p.G.max())],
        "pitches_per_game_p05_p50_p95": q(p.pitches_per_game),
        "icc_r_p05_p50_p95": q(p.icc_r), "icc_d_p05_p50_p95": q(p.icc_d),
        "u_excess_kurtosis_p05_p50_p95": q(p.u_excess_kurtosis),
        "psi_excess_kurtosis_p05_p50_p95": q(p.psi_excess_kurtosis),
    }


def small_players(df: pd.DataFrame) -> dict:
    s = df.groupby("batter_id").agg(n=("game_id", "size"), G=("game_id", "nunique"))
    low = s[(s.n >= 100) & (s.n < 300)]
    return {"players": int(len(low)), "G_min_p50_max": [int(low.G.min()), float(low.G.median()), int(low.G.max())],
            "G_below_20": int((low.G < 20).sum())}


# 4. 신장 -----------------------------------------------------------------

def heights() -> dict:
    snap = json.loads((GPT / "kbo_heights.json").read_text())
    ok = {r["player_id"]: r["height_cm"] for r in snap if r["status"] == "ok"}
    bad = {r["player_id"]: r["status"] for r in snap if r["status"] != "ok"}
    out = {"snapshot_ids": len(snap), "ok": len(ok), "not_ok": bad,
           "ok_height_min_p50_max": [min(ok.values()), float(np.median(list(ok.values()))), max(ok.values())],
           "seasons": {}, "abs_implied": {}}
    implied = {}
    for year in range(2019, 2027):
        t = load_table(ROOT, "pitches", year, columns=["batter_id", "sz_top", "sz_bottom"]).to_pandas()
        t["batter_id"] = t.batter_id.astype(str)
        n = t.groupby("batter_id").size()
        has = n.index.isin(list(ok))
        big = n >= 300
        out["seasons"][str(year)] = {
            "batters": int(len(n)), "batters_with_height": int(has.sum()),
            "pitch_share_with_height": float(n[has].sum() / n.sum()),
            "batters_300": int(big.sum()), "batters_300_with_height": int((has & big).sum()),
            "missing_ids_300": sorted(n[big & ~has].index.tolist())}
        if year not in ABS_RATIO:
            continue
        t = t.dropna()
        g = t.groupby("batter_id")
        med = g[["sz_top", "sz_bottom"]].median() * CM
        top, bottom = ABS_RATIO[year]
        h = pd.DataFrame({"h_top": med.sz_top / top, "h_bottom": med.sz_bottom / bottom, "n": g.size(),
                          "unique_top": g.sz_top.nunique()})
        h = h[h.index.isin(list(ok))]
        h["profile"] = [ok[i] for i in h.index]
        diff = h.h_top - h.profile
        implied[year] = h
        w = h.n / h.n.sum()
        out["abs_implied"][str(year)] = {
            "ratios": [top, bottom], "batters": int(len(h)),
            "corr_implied_profile": float(h.h_top.corr(h.profile)), "sd_implied_cm": float(h.h_top.std()),
            "sd_profile_cm": float(h.profile.std()), "sd_diff_cm": float(diff.std()),
            "top_vs_bottom_implied_max_abs_cm": float((h.h_top - h.h_bottom).abs().max()),
            "share_abs_diff_le_0_5cm": float((diff.abs() <= .5).mean()), "share_abs_diff_le_1cm": float((diff.abs() <= 1).mean()),
            "share_abs_diff_le_2cm": float((diff.abs() <= 2).mean()),
            "pitch_share_abs_diff_le_1cm": float(w[diff.abs() <= 1].sum()),
            "diff_p05_p50_p95_cm": q(diff), "diff_min_max_cm": [float(diff.min()), float(diff.max())],
            "batters_300": int((h.n >= 300).sum()), "batters_300_share_abs_diff_le_1cm": float((diff[h.n >= 300].abs() <= 1).mean()),
            "batters_multiple_zone_values": int((h.unique_top > 1).sum()),
            "largest_diffs": [{"batter_id": i, "implied_cm": round(float(h.h_top[i]), 2), "profile_cm": int(h.profile[i]), "pitches": int(h.n[i])}
                              for i in diff.abs().sort_values(ascending=False).index[:8]]}
    for a, b in ((2024, 2025), (2025, 2026), (2024, 2026)):
        both = implied[a].index.intersection(implied[b].index)
        change = implied[b].h_top.loc[both] - implied[a].h_top.loc[both]
        out["abs_implied"][f"{a}_to_{b}_implied_change"] = {
            "batters": int(len(both)), "share_abs_change_le_0_5cm": float((change.abs() <= .5).mean()),
            "share_abs_change_gt_1cm": float((change.abs() > 1).mean()), "change_p05_p50_p95_cm": q(change)}
    return out


# 5. ABS 끝면 1.5cm --------------------------------------------------------

def back_plane(df: pd.DataFrame) -> dict:
    """현행: top=max(z_mid,z_back)−top, bottom=min(z_mid,z_back)−bottom. 공식: 끝면 기준만 1.5cm 낮다.
    공식 top=max(z_mid−top, z_back−top+1.5), bottom=min(z_mid−bottom, z_back−bottom+1.5).
    낙하 drop=z_mid−z_back ≥ 0이면 공식−현행은 top +max(0,1.5−drop), bottom +min(drop,1.5)."""
    v = df[~df.plane_fallback.astype(bool)]
    hi = v.top_gap_cm + v.sz_top * CM
    lo = v.bottom_gap_cm + v.sz_bottom * CM
    drop = hi - lo  # max−min = |z_mid − z_back|. 상승 궤적이면 부호를 알 수 없어 여기서 보고만 한다
    d_top, d_bottom = np.maximum(0, BACK_OFFSET_CM - drop), np.minimum(drop, BACK_OFFSET_CM)
    takes = v.swing.to_numpy() == 0
    flip_bottom = (v.bottom_gap_cm < 0) & (v.bottom_gap_cm + d_bottom >= 0)
    flip_top = (v.top_gap_cm <= 0) & (v.top_gap_cm + d_top > 0)
    return {
        "eligible": int(len(df)), "fallback_share": float(df.plane_fallback.astype(bool).mean()),
        "mid_back_height_diff_cm_p01_p05_p50_p95": q(drop, (.01, .05, .5, .95)),
        "share_diff_ge_1_5cm": float((drop >= BACK_OFFSET_CM).mean()),
        "bottom_shift_cm_mean": float(d_bottom.mean()), "top_shift_cm_mean": float(d_top.mean()),
        "share_bottom_shift_exactly_1_5": float((d_bottom == BACK_OFFSET_CM).mean()),
        "center_rule_flip_share_all": float((flip_bottom | flip_top).mean()),
        "center_rule_flip_share_takes": float((flip_bottom | flip_top)[takes].mean()),
        "center_rule_flip_bottom_takes": int(flip_bottom[takes].sum()), "center_rule_flip_top_takes": int(flip_top[takes].sum()),
        "takes": int(takes.sum()),
        "note": "공 반지름 미반영 중심 기준. 콜·p_zone·정확성을 계산하지 않았다",
    }


def main() -> None:
    df = pitches_2026()
    out = {"source_commit": SOURCE, "pitch_sha256": PITCH_SHA,
           "python": sys.version.split()[0], "versions": {m.__name__: m.__version__ for m in (np, pd)},
           "b1_synthetic": synthetic(), "b1_empirical": empirical(df), "players_100_299": small_players(df),
           "heights": heights(), "abs_back_plane_2026": back_plane(df)}
    (HERE / "cross_check.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
