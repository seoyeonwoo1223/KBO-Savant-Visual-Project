"""기존 APR·ZA 산식과 저장 기록의 읽기 전용 재현. 신규 후보 실험은 하지 않는다.

실행: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src OMP_NUM_THREADS=2
      OPENBLAS_NUM_THREADS=2 python3.12 analysis/apr_za_review_20261003/reproduce.py
출력은 이 파일과 같은 폴더의 results/로 고정한다.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "results"
BASE_COMMIT = "d7bb6fa1"
INPUTS: dict[str, str] = {}


def track(relative: str) -> Path:
    path = ROOT / relative
    if relative not in INPUTS:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        INPUTS[relative] = digest.hexdigest()
    return path


def read_json(relative: str):
    return json.loads(track(relative).read_text(encoding="utf-8"))


def corr(a, b, method="spearman"):
    return float(pd.Series(np.asarray(a)).corr(pd.Series(np.asarray(b)), method=method))


def plus_index(table, value, se, level, league_mean):
    """_plus_index의 독립 구현: 입력 반올림은 호출자가 결정한다."""
    n = table.n.to_numpy(dtype=float)
    centered = table[value].to_numpy(dtype=float) - league_mean
    error = table[se].to_numpy(dtype=float)
    q = n >= 300
    sigma2 = float(np.median(error[q] ** 2 * n[q]))
    tau2 = float(np.var(centered[q], ddof=1) - np.mean(error[q] ** 2))
    k = sigma2 / tau2 if tau2 > 0 else np.inf
    shrunk = n / (n + k) * centered if np.isfinite(k) else np.zeros(len(n))
    shrunk -= np.average(shrunk, weights=n)
    score = 100 * (level + shrunk) / level
    reference = np.sort(score[q])
    low = np.searchsorted(reference, score, "left")
    high = np.searchsorted(reference, score, "right")
    percentile = 100 * (low + .5 * (high - low)) / len(reference)
    return pd.DataFrame({"score": score, "percentile": percentile}, index=table.index), {
        "k": None if not np.isfinite(k) else float(k), "sigma2": sigma2, "tau2": tau2,
        "qualified": int(q.sum()), "pitch_weighted_index": float(np.average(score, weights=n))}


def cluster_mean(ev, values):
    t = pd.DataFrame({"b": ev.batter_id, "g": ev.game_id, "v": values})
    g = t.groupby("b", sort=True)
    n, mean = g.size(), g.v.mean()
    t["dev"] = t.v - t.b.map(mean)
    cluster_sums = t.groupby(["b", "g"]).dev.sum()
    se = np.sqrt((cluster_sums ** 2).groupby(level=0).sum()) / n
    return pd.DataFrame({"n": n, "value": 100 * mean, "se": 100 * se})


def csv_out(name, table):
    table.to_csv(OUT / name, index=False, float_format="%.12g", lineterminator="\n")


def public_reproduction():
    boards, rows = {}, []
    small_deltas, qualified_scores = [], []
    for year in range(2019, 2027):
        board = read_json(f"web/data/zone_awareness/{year}/leaderboard.json")
        columns = ["batter_id", "pitches_seen", "qualified_300", "jdv_per_100", "jdv_se",
                   "zj_per_100", "zj_se", "apr", "apr_percentile", "za_plus", "za_percentile",
                   "swing_aggression", "za_raw"]
        t = pd.DataFrame(board["players"])[columns].rename(columns={"pitches_seen": "n"})
        t["batter_id"] = t.batter_id.astype(str)
        t = t.set_index("batter_id").sort_index()
        boards[year] = t
        am, zm = board["apr"], board["za_plus"]
        apr, ap = plus_index(t, "jdv_per_100", "jdv_se", am["league_dv_per_100"], am["league_jdv_per_100"])
        za, zp = plus_index(t, "zj_per_100", "zj_se", zm["league_margin_per_100"], zm["league_zj_per_100"])
        q = t.n >= 300
        raw_za_plus = 100 * (zm["league_margin_per_100"] + t.zj_per_100 - zm["league_zj_per_100"]) / zm["league_margin_per_100"]
        small = (t.n >= 300) & (t.n <= 600)
        diffs = (raw_za_plus - t.za_plus).abs()
        small_deltas.extend(diffs[small].to_list())
        qualified_scores.extend(zip(t.za_plus[q], raw_za_plus[q]))
        rows.append({"season": year, "model_version": board["model_version"], "players": len(t), "pitches": int(t.n.sum()),
                     "qualified": int(q.sum()), "qualified_flag_matches_n": bool((q == t.qualified_300).all()),
                     "L": am["league_dv_per_100"], "M": zm["league_margin_per_100"],
                     "apr_k_stored": am["shrinkage_k_pitches"], "apr_k_recomputed": ap["k"],
                     "apr_sigma2": ap["sigma2"], "apr_tau2": ap["tau2"],
                     "apr_max_score_error": float((apr.score - t.apr).abs().max()),
                     "apr_max_percentile_error": float((apr.percentile - t.apr_percentile).abs().max()),
                     "apr_pitch_weighted_mean": ap["pitch_weighted_index"],
                     "za_k_stored": zm["shrinkage_k_pitches"], "za_k_recomputed": zp["k"],
                     "za_sigma2": zp["sigma2"], "za_tau2": zp["tau2"],
                     "za_max_score_error": float((za.score - t.za_plus).abs().max()),
                     "za_max_percentile_error": float((za.percentile - t.za_percentile).abs().max()),
                     "za_pitch_weighted_mean": zp["pitch_weighted_index"],
                     "apr_sa_spearman": corr(t.apr[q], t.swing_aggression[q]),
                     "za_plus_sa_spearman": corr(t.za_plus[q], t.swing_aggression[q]),
                     "za_raw_sa_spearman": corr(t.za_raw[q], t.swing_aggression[q]),
                     "za_raw_vs_shrunk_rho_qualified": corr(raw_za_plus[q], t.za_plus[q]),
                     "za_raw_vs_shrunk_rho_all": corr(raw_za_plus, t.za_plus),
                     "small_300_600_players": int(small.sum()), "small_za_mean_absolute_point_change": float(diffs[small].mean()),
                     "apr_std_qualified_ddof1": float(t.apr[q].std(ddof=1))})
    result = pd.DataFrame(rows)
    csv_out("public_seasons.csv", result)
    return boards, result, {"판정": "확인함(저장 리더보드 산식 독립 재계산)",
        "수축제거_300_600구_통합평균_절대점수변화": float(np.mean(small_deltas)),
        "수축제거_300_600구_통합타자시즌수": len(small_deltas),
        "수축제거_규정타자_시즌합동rho": corr([s[0] for s in qualified_scores], [s[1] for s in qualified_scores]),
        "수축제거_시즌별rho_평균": float(result.za_raw_vs_shrunk_rho_qualified.mean()),
        "주의": "수축 제거는 저장된 기존 ZA+ 구성의 표시 감사다. 새 산식 채택 실험이 아니다. 순위 모집단별 rho와 300≤n≤600의 평균 절대차를 따로 보고한다.",
        "시즌": rows}


def existing_record_reproduction(boards):
    x = read_json("analysis/sbj_formula/results/x_compare.json")
    seasons, zrows = [], []
    for year in range(2019, 2027):
        t = pd.read_csv(track(f"analysis/sbj_formula/results/x_compare_{year}.csv"), dtype={"batter_id": str},
                        usecols=["batter_id", "n", "sa", "A_apr", "B_apr_neutral", "D_za"])
        reference = boards[year]
        archived = t.set_index("batter_id")
        ids = archived.index.intersection(reference.index)
        row = {"season": year, "qualified": len(t), "minimum_n": int(t.n.min()),
               "A_sa_spearman": corr(t.A_apr, t.sa), "B_sa_spearman": corr(t.B_apr_neutral, t.sa),
               "D_za_sa_spearman": corr(t.D_za, t.sa), "A_std_ddof1": float(t.A_apr.std(ddof=1)),
               "B_std_ddof1": float(t.B_apr_neutral.std(ddof=1)),
               "current_public_n_mismatched_players": int((archived.loc[ids, "n"] != reference.loc[ids, "n"]).sum()),
               "current_public_n_max_difference": int((archived.loc[ids, "n"] - reference.loc[ids, "n"]).abs().max()),
               "current_public_A_max_score_difference": float((archived.loc[ids, "A_apr"] - reference.loc[ids, "apr"]).abs().max()),
               "current_public_D_max_raw_difference": float((archived.loc[ids, "D_za"] - reference.loc[ids, "za_raw"]).abs().max())}
        for candidate, key in (("A_apr", "A_sa_spearman"), ("B_apr_neutral", "B_sa_spearman"), ("D_za", "D_za_sa_spearman")):
            row[key + "_stored"] = x["candidates"][candidate]["X2_spearman_sa_by_season"][str(year)]
            row[key + "_error"] = row[key] - row[key + "_stored"]
        seasons.append(row)
        z = pd.read_csv(track(f"analysis/sbj_formula/results/zb_neutral_za_{year}.csv"),
                        dtype={"batter_id": str}, usecols=["batter_id", "Z0", "N0", "sa"])
        # Z0 - N0 = SA * mean(2*p_zone-1). 이전 검토와 동일하게 |SA| ≥ 0.2 %p만 사용한다.
        keep = z.sa.abs() >= .2
        inferred = (z.Z0 - z.N0) / z.sa
        bound = (1e-4 + inferred.abs() * 5e-5) / (z.sa.abs() - 5e-5)
        zrows.append({"season": year, "source_players": len(z), "included_abs_sa_ge_0_2": int(keep.sum()),
                      "zbar_median_inferred": float(inferred[keep].median()),
                      "zbar_median_abs_error_bound": float(bound[keep].median()),
                      "zbar_max_abs_error_bound": float(bound[keep].max()),
                      "za_policy_term_std": float((z.Z0 - z.N0).std(ddof=1)),
                      "za_policy_term_variance_ratio": float((z.Z0 - z.N0).var(ddof=1) / z.Z0.var(ddof=1)),
                      "za_policy_term_covariance_share": float(np.cov(z.Z0 - z.N0, z.Z0, ddof=1)[0, 1] / z.Z0.var(ddof=1)),
                      "za_raw_std": float(z.Z0.std(ddof=1)),
                      "za_raw_vs_N0_spearman": corr(z.Z0, z.N0)})
    csv_out("x_seasons.csv", pd.DataFrame(seasons))
    csv_out("za_policy_decomposition_from_csv.csv", pd.DataFrame(zrows))
    records = {}
    for name in ("z_weighted_za", "zb_neutral_za", "zb_neutral_za_recenter", "zb_neutral_za_strike"):
        d = read_json(f"analysis/sbj_formula/results/{name}.json")
        records[name] = {k: d[k] for k in ("candidates", "recommended", "recommended_zd", "passing", "external", "ZG7_mean") if k in d}
    return {"판정": "확인함(CSV 상관·표준편차 재계산과 JSON 기록 열람을 구분)",
            "CSV_정밀도": "X/Z CSV는 소수 4자리. 과거 zbar는 (Z0-N0)/SA 역산이며 표본·오차한계를 명시했다.",
            "X_저장결과": {k: x[k] for k in ("pairs", "batters", "candidates", "passing", "recommended")},
            "X_원자료독립재현불가": "반분 신뢰도·다음 시즌 회귀/CI는 과거 투구·외부 PA 원자료를 재빌드하지 않으므로 저장 JSON 대조에 한정. 과거 B k는 CSV에 SE와 B 원입력이 없어 식별 불가.",
            "X_CSV_재계산": seasons, "Z_저장결과": records, "ZA_공격성항": zrows}


def pitch_reproduction(boards):
    columns = ["game_id", "batter_id", "swing", "p_swing", "p_zone", "judgment", "delta_v", "dv", "region", "strikes_before"]
    ev = pq.read_table(track("data/metrics/zone_awareness/2026/pitches.parquet"), columns=columns).to_pandas()
    ev["batter_id"] = ev.batter_id.astype(str)
    ev["r"] = ev.swing - ev.p_swing
    ev["z"] = 2 * ev.p_zone - 1
    g = ev.groupby("batter_id", sort=True)
    ev["m"] = g.r.transform("mean")
    ev["jdv_A"] = 2 * ev.r * ev.delta_v
    ev["jdv_B"] = 2 * (ev.r - ev.m) * ev.delta_v
    ev["zj"] = 2 * ev.judgment
    summary = pd.DataFrame({"n": g.size(), "SA": 100 * g.r.mean(), "zbar": g.z.mean(),
                            "deltabar": g.delta_v.mean(), "two_strike_share": (ev.strikes_before == 2).groupby(ev.batter_id).mean(),
                            "dv_per_100": 100 * g.dv.mean(), "za_raw": 100 * g.judgment.mean()})
    A, B, Z = [cluster_mean(ev, ev[c]) for c in ("jdv_A", "jdv_B", "zj")]
    board = boards[2026]
    for name, t in (("A", A), ("B", B), ("ZA", Z)):
        summary[name + "_input_per_100"] = t.value
        summary[name + "_se_naive_cluster"] = t.se
    # X는 반올림 전 타자 입력으로 add_apr를 호출한다. 공개 profile_summary는 입력을 6자리로 먼저 반올림한다.
    L = 100 * float(ev.dv.mean())
    aplus, am = plus_index(A, "value", "se", L, 100 * float(ev.jdv_A.mean()))
    bplus, bm = plus_index(B, "value", "se", L, 100 * float(ev.jdv_B.mean()))
    zplus, zm = plus_index(Z, "value", "se", 100 * float(((2 * ev.swing - 1) * ev.z).mean()), 100 * float(ev.zj.mean()))
    summary["APR_A_X_definition"] = aplus.score
    summary["APR_B_X_definition"] = bplus.score
    summary["ZA_plus_unrounded_input"] = zplus.score
    summary["APR_policy_term"] = 2 * summary.SA * summary.deltabar
    summary["ZA_policy_term"] = summary.SA * summary.zbar
    summary["ZA_within_covariance"] = summary.za_raw - summary.ZA_policy_term
    q = summary.n >= 300
    match = summary.index.intersection(board.index)
    errors = {"n": int((summary.loc[match, "n"] - board.loc[match, "n"]).abs().max()),
              "SA": float((summary.loc[match, "SA"] - board.loc[match, "swing_aggression"]).abs().max()),
              "za_raw": float((summary.loc[match, "za_raw"] - board.loc[match, "za_raw"]).abs().max()),
              "A_input_per_100": float((summary.loc[match, "A_input_per_100"] - board.loc[match, "jdv_per_100"]).abs().max()),
              "A_se": float((summary.loc[match, "A_se_naive_cluster"] - board.loc[match, "jdv_se"]).abs().max()),
              "ZA_input_per_100": float((summary.loc[match, "ZA_input_per_100"] - board.loc[match, "zj_per_100"]).abs().max()),
              "ZA_se": float((summary.loc[match, "ZA_se_naive_cluster"] - board.loc[match, "zj_se"]).abs().max())}
    a_public, _ = plus_index(A.round({"value": 6, "se": 6}), "value", "se", L, 100 * float(ev.jdv_A.mean()))
    z_public, _ = plus_index(Z.round({"value": 6, "se": 6}), "value", "se",
                            100 * float(((2 * ev.swing - 1) * ev.z).mean()), 100 * float(ev.zj.mean()))
    errors["public_APR_score"] = float((a_public.loc[match, "score"] - board.loc[match, "apr"]).abs().max())
    errors["public_ZA_plus_score"] = float((z_public.loc[match, "score"] - board.loc[match, "za_plus"]).abs().max())
    x = pd.read_csv(track("analysis/sbj_formula/results/x_compare_2026.csv"), dtype={"batter_id": str},
                    usecols=["batter_id", "A_apr", "B_apr_neutral", "D_za"]).set_index("batter_id")
    x_ids = x.index.intersection(summary.index)
    errors["X_A_score"] = float((summary.loc[x_ids, "APR_A_X_definition"] - x.loc[x_ids, "A_apr"]).abs().max())
    errors["X_B_score"] = float((summary.loc[x_ids, "APR_B_X_definition"] - x.loc[x_ids, "B_apr_neutral"]).abs().max())
    errors["X_D_za"] = float((summary.loc[x_ids, "za_raw"] - x.loc[x_ids, "D_za"]).abs().max())
    contributions = (100 * ev.judgment).groupby([ev.batter_id, ev.region]).sum().unstack(fill_value=0).div(summary.n, axis=0)
    total_q = summary.za_raw[q]
    region_shares = {region: float(np.cov(contributions.loc[total_q.index, region], total_q, ddof=1)[0, 1] / total_q.var(ddof=1))
                     for region in contributions.columns}
    region_shares["shadow_total"] = region_shares["shadow_in"] + region_shares["shadow_out"]
    sum_error = float((contributions.sum(axis=1) - summary.za_raw).abs().max())
    jdv_regions = (100 * ev.jdv_A).groupby([ev.batter_id, ev.region]).sum().unstack(fill_value=0).div(summary.n, axis=0)
    jdv_actions = (100 * ev.jdv_A).groupby([ev.batter_id, ev.swing]).sum().unstack(fill_value=0).div(summary.n, axis=0)
    summary = summary.join(contributions.add_prefix("za_region_"))
    csv_out("pitches_2026_player_summary.csv", summary.reset_index())
    cq = summary[q]
    term, raw = cq.APR_policy_term, cq.A_input_per_100
    return {"판정": "확인함(2026 필요한 열만 투구별 독립 재계산)", "투구읽기열": columns,
            "투구수": len(ev), "타자수": len(summary), "규정타자수": int(q.sum()), "공개와X_최대오차": errors,
            "APR_A_X_수축": am, "APR_B_X_수축": bm, "ZA_수축": zm,
            "APR_B_k_주의": "기존 X 정의의 동일 표본 m 및 기존 naive cluster SE로 재현했다. 올바른 영향함수 SE와의 비교 실험은 실행하지 않았다.",
            "APR_B_X_규정표준편차_ddof1": float(cq.APR_B_X_definition.std(ddof=1)),
            "APR_A_X_규정표준편차_ddof1": float(cq.APR_A_X_definition.std(ddof=1)),
            "현재2026_APR_A_SA_spearman": corr(cq.APR_A_X_definition, cq.SA),
            "현재2026_APR_B_SA_spearman": corr(cq.APR_B_X_definition, cq.SA),
            "APR_A_B_분해최대오차": float((summary.A_input_per_100 - summary.B_input_per_100 - summary.APR_policy_term).abs().max()),
            "규정타자_중앙값_100delta": float((100 * cq.deltabar).median()), "규정타자_중앙값_zbar": float(cq.zbar.median()),
            "APR_공격성항_SA_spearman": corr(term, cq.SA), "APR_공격성항_SA_pearson": corr(term, cq.SA, "pearson"),
            "APR_공격성항_variance_ratio": float(term.var(ddof=1) / raw.var(ddof=1)),
            "APR_공격성항_covariance_share": float(np.cov(term, raw, ddof=1)[0, 1] / raw.var(ddof=1)),
            "분산정의": "variance_ratio=Var(항)/Var(전체)는 가법적이지 않다. covariance_share=Cov(항,전체)/Var(전체)는 분해 항의 합이 1이며 인과 설명률이 아니다.",
            "ZA_구역별_covariance_share": region_shares, "ZA_구역합_최대오차": sum_error,
            "APR_구역합_최대오차": float((jdv_regions.sum(axis=1) - summary.A_input_per_100).abs().max()),
            "APR_행동합_최대오차": float((jdv_actions.sum(axis=1) - summary.A_input_per_100).abs().max()),
            "ZA_plus_2스트라이크비중_spearman": corr(cq.ZA_plus_unrounded_input, cq.two_strike_share),
            "ZA_raw_2스트라이크비중_spearman": corr(cq.za_raw, cq.two_strike_share),
            "ZA_plus_2스트라이크비중_pearson": corr(cq.ZA_plus_unrounded_input, cq.two_strike_share, "pearson")}


def main():
    # 데이터 접근 순서: 요약 → 스키마 → 필요한 열·행. 원문·partition-index는 열지 않는다.
    read_json("data/curated/summary.json")
    read_json("data/curated/schema.json")
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("재현 기준은 Python 3.12다.")
    if os.environ.get("PYTHONPATH") != "src":
        raise RuntimeError("PYTHONPATH를 src로 설정해야 한다.")
    if any(os.environ.get(name) != "2" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS")):
        raise RuntimeError("OMP_NUM_THREADS와 OPENBLAS_NUM_THREADS를 2로 설정해야 한다.")
    for line in track("constraints-za.txt").read_text(encoding="utf-8").splitlines():
        if "==" in line:
            name, expected = line.split("==")
            actual = importlib.metadata.version(name)
            if actual != expected:
                raise RuntimeError(f"고정 패키지 버전 불일치: {name} {actual} != {expected}")
    OUT.mkdir(exist_ok=True)
    source = track("src/visualbaseball/zone_decision.py").read_text(encoding="utf-8")
    version = re.search(r"MODEL_VERSION\s*=\s*['\"]([^'\"]+)", source).group(1)
    track("analysis/sbj_formula/x_compare.py")
    track("analysis/sbj_formula/zb_neutral_za.py")
    track("analysis/sbj_formula/gates.md")
    track("analysis/apr_za_review_20261003/verification_plan.md")
    track("analysis/apr_za_review_20261003/reproduce.py")
    track("requirements.txt")
    track("constraints-za.txt")
    boards, public, shrink = public_reproduction()
    record = existing_record_reproduction(boards)
    pitches = pitch_reproduction(boards)
    # 계산 전에 커밋한 감사 문턱만 적용한다. 버전 불일치는 숨기지 않는다.
    def relative_k_error(kind):
        return float(((public[f"{kind}_k_recomputed"] - public[f"{kind}_k_stored"]).abs()
                      / public[f"{kind}_k_stored"].abs()).max())

    v2_score = float(max(public.apr_max_score_error.max(), public.za_max_score_error.max()))
    v2_k = max(relative_k_error("apr"), relative_k_error("za"))
    v3_errors = pitches["공개와X_최대오차"]
    v3 = max(value for key, value in v3_errors.items() if not key.startswith("X_"))
    v4 = max(abs(row[key]) for row in record["X_CSV_재계산"]
             for key in ("A_sa_spearman_error", "B_sa_spearman_error", "D_za_sa_spearman_error"))
    audit = {
        "V1": {"요청버전과일치": version == "za7.8-neutral-apr",
               "운영과후보분리": True, "공개와소스일치": bool((public.model_version == version).all())},
        "V2": {"통과": v2_score <= 1e-4 and v2_k <= 1e-4,
               "최대점수오차": v2_score, "최대k상대오차": v2_k},
        "V3": {"통과": v3 <= 1e-4 and
                         max(pitches[key] for key in ("ZA_구역합_최대오차", "APR_구역합_최대오차", "APR_행동합_최대오차")) <= 1e-4,
               "공개집계최대오차": v3, "X스냅샷과일치": False},
        "V4": {"상관문턱통과": v4 <= .0002, "최대상관오차": v4,
               "과거B_k": "원자료 부족으로 미확인"},
        "V5": "확인함: 저장 기록 대조만 수행. 신뢰도·회귀 CI·외부 47점의 원자료 독립 재현은 미실행.",
        "V6": "확인함: 2026 기존 점수 요약만. 존 높이 결과는 height_audit.json에 있으며 원인 판정은 미확인.",
        "V7": "반복 실행의 바이트 동일성은 별도 verification.json에 기록한다.",
    }
    result = {"기준커밋": BASE_COMMIT, "코드모델버전": version, "요청모델버전": "za7.8-neutral-apr",
              "버전판정": "확인함: 체크아웃 코드는 A 산식의 za7.7-zaplus이고 공개 8시즌 버전도 같다. B는 기존 X 후보값으로 분리했다.",
              "실행환경": {"python_major_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
                          "OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2", "패키지":
                          {p: importlib.metadata.version(p) for p in ("numpy", "pandas", "pyarrow", "scipy", "scikit-learn", "openpyxl")}},
              "사전감사기준판정": audit,
              "공개집계_산식감사": shrink, "기존기록감사": record, "2026투구별감사": pitches,
              "입력_SHA256": dict(sorted(INPUTS.items()))}
    (OUT / "reproduction.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    if not (audit["V1"]["공개와소스일치"] and audit["V2"]["통과"] and audit["V3"]["통과"] and audit["V4"]["상관문턱통과"]):
        raise RuntimeError("사전 감사 문턱에 미달했다. 결과 파일의 실패 판정을 확인해야 한다.")
    print(json.dumps({"코드모델": version, "공개모델": sorted(set(public.model_version)),
                      "공개최대점수오차": float(max(public.apr_max_score_error.max(), public.za_max_score_error.max())),
                      "ZA수축제거_300_600구_통합평균절대차": shrink["수축제거_300_600구_통합평균_절대점수변화"],
                      "2026_B_k": pitches["APR_B_X_수축"]["k"], "2026_재현오차": pitches["공개와X_최대오차"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
