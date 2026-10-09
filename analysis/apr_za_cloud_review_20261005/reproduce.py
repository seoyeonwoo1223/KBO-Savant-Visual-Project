"""고정 Git 객체의 기존 산식만 재현한다. 신규 후보 적합·성능 실험은 하지 않는다."""
from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import re
import subprocess
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = "6495992497af77df9abef861d235443a3302f130"
REVIEWS = {
    "초기_ZA": "da2614816c975f2063033f121b9295a7da1bcec9",
    "APR_ZA": "ca8de0fd5ceefec514a3ee1394d0ac01db0da008",
}
INPUTS = {}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def read(path, commit=BASE):
    blob = git("show", f"{commit}:{path}")
    INPUTS[f"{commit}:{path}"] = {
        "sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob)
    }
    return blob


def js(path, commit=BASE):
    return json.loads(read(path, commit))


def corr(a, b):
    return {"pearson": float(a.corr(b)), "spearman": float(a.corr(b, method="spearman"))}


def plus(t, value, se, level, league):
    """운영 helper를 호출하지 않는 독립 적률·수축·표시 계산."""
    n = t.n.to_numpy(float)
    q = n >= 300
    v = t[value].to_numpy(float) - league
    e = t[se].to_numpy(float)
    sigma = float(np.median(e[q] ** 2 * n[q]))
    tau = float(np.var(v[q], ddof=1) - np.mean(e[q] ** 2))
    k = sigma / tau if tau > 0 else np.inf
    s = n / (n + k) * v if np.isfinite(k) else np.zeros(len(n))
    s -= np.average(s, weights=n)
    return pd.Series(100 * (level + s) / level, index=t.index), {
        "k": float(k), "sigma2": sigma, "tau2": tau,
    }


def cluster_se(frame, values):
    sums = pd.Series(values, index=frame.index).groupby(frame.game_id).sum()
    return float(np.sqrt(np.sum(sums.to_numpy() ** 2)) / len(frame))


def algebra():
    r = np.array([.4, -.2, .1, -.5]); z = np.array([1., -1., 1., -1.])
    x = r-r.mean(); c = 1.67; a = (1+c)/2; b = (1-c)/2
    w = np.where(z >= 0, 1., c)
    binary_error = abs(np.sum(w*x*z) - (1+c)*np.sum(x[z > 0]))
    mix_error = abs(np.mean(w*r*z) - (a*np.mean(r*z)+b*np.mean(r)))
    z = np.array([.8, -.3, .2, -.9]); w = np.where(z >= 0, 1., c)
    continuous_error = abs(np.mean(w*x*z) - (a*np.mean(x*z)+b*np.mean(x*abs(z))))
    xa = np.array([.5, -.5]); za = np.array([.9, -.1]); zb = np.array([.4, -.4])
    reversal = {str(k): [float(np.mean(np.where(v >= 0, 1., k)*xa*v)) for v in (za, zb)] for k in (1, 3)}
    f = pd.DataFrame({"game_id": ["a", "a", "b", "b"]})
    d = np.full(4, .3); cov = np.mean(x*(d-d.mean()))
    correct = 200*(x*(d-d.mean())-cov)
    naive = 200*(x*d-np.mean(x*d))
    result = {"binary_neutral_sum_error": float(binary_error), "binary_sa_mixture_error": float(mix_error),
              "continuous_remainder_error": float(continuous_error), "rank_reversal": reversal,
              "constant_delta_B": float(200*cov), "constant_delta_IF_SE": cluster_se(f, correct),
              "constant_delta_naive_SE": cluster_se(f, naive)}
    assert max(binary_error, mix_error, continuous_error) < 1e-12
    assert result["constant_delta_B"] == result["constant_delta_IF_SE"] == 0
    # 평균 두 개의 공동 추정: 관측치 질량을 조금 늘린 수치 미분 검산.
    dd = np.array([.2, -.1, .4, -.3]); cov0 = np.mean(x*(dd-dd.mean()))
    derivatives = []
    eps = 1e-6
    for i in range(len(r)):
        ww = np.full(len(r), (1-eps)/len(r)); ww[i] += eps
        c1 = np.average((r-np.average(r, weights=ww))*(dd-np.average(dd, weights=ww)), weights=ww)
        derivatives.append((200*c1-200*cov0)/eps)
    psi = 200*((r-r.mean())*(dd-dd.mean())-cov0)
    result["IF_finite_difference_max_error"] = float(np.max(abs(np.array(derivatives)-psi)))
    assert result["IF_finite_difference_max_error"] < 1e-4
    return result


def main():
    assert os.environ.get("PYTHONPATH") == "src"
    assert os.environ.get("OMP_NUM_THREADS") == "2"
    constraints = read("constraints-za.txt").decode()
    pinned = dict(re.findall(r"^([\w-]+)==([^\s]+)$", constraints, re.M))
    actual = {name: version(name) for name in pinned}
    assert actual == pinned, (actual, pinned)
    summary = js("data/curated/summary.json")
    schema = js("data/curated/schema.json")
    src = read("src/visualbaseball/zone_decision.py").decode()
    result = {"base_commit": BASE, "model_version": re.search(r"MODEL_VERSION = '([^']+)'", src)[1],
              "environment": {"python": platform.python_version(), "packages": actual,
                              "PYTHONPATH": os.environ["PYTHONPATH"], "OMP_NUM_THREADS": os.environ["OMP_NUM_THREADS"]},
              "curated": {"generated_at": summary["generated_at"], "season_2026": summary["seasons"]["2026"],
                          "summary_schema_sha256": summary["schema_sha256"],
                          "schema_declared_sha256": schema["schema_sha256"],
                          "schema_file_sha256": hashlib.sha256(read("data/curated/schema.json")).hexdigest()},
              "versions": {}, "algebra": algebra()}
    report = js("data/metrics/zone_awareness/2026/report.json")
    for path in ("src/visualbaseball/curated.py", "src/visualbaseball/parser.py"):
        assert (ROOT/path).read_bytes() == read(path), "스키마 검산 소스는 기준 Git 객체와 같아야 한다"
    from visualbaseball.curated import schema_sha256
    runtime_schema = schema_sha256()
    result["curated"]["runtime_schema_sha256"] = runtime_schema
    result["curated"]["summary_runtime_schema_match"] = runtime_schema == summary["schema_sha256"]
    result["curated"]["schema_document_runtime_match"] = runtime_schema == schema["schema_sha256"]
    result["operational_report_2026"] = {"model_version": report["model_version"], "pitches": report["pitches"],
        "latest_game": report["source"]["latest_game"], "excluded": report["source"]["excluded"],
        "reproducibility": report["reproducibility"],
        "date_blocks": [{k: f[k] for k in ("start", "end", "pitches")} for f in report["crossfit_blocks"]]}
    source_matches = {}
    for name, expected in report["reproducibility"]["source_sha256"].items():
        assert name in ("zone_decision.py", "plate_decision_v1.py", "swing_take.py", "pitch_types.py", "batter_stance.py")
        source_matches[name] = hashlib.sha256(read(f"src/visualbaseball/{name}")).hexdigest() == expected
    assert all(source_matches.values())
    result["operational_report_2026"]["source_hash_matches_base"] = source_matches
    for label, commit in {"기준": BASE, **REVIEWS, "초기_기준": "f0dc0a44367852cc1aea86d8eb24dcdb1a19d413", "APR_문서_기준": "d7bb6fa1"}.items():
        s = read("src/visualbaseball/zone_decision.py", commit).decode()
        result["versions"][label] = {"commit": git("rev-parse", commit).decode().strip(),
                                      "model": re.search(r"MODEL_VERSION = '([^']+)'", s)[1],
                                      "profile_B": "excess-excess.mean()" in s}
    for path in ("analysis/sbj_formula/gates.md", "analysis/sbj_formula/zb_neutral_za.py",
                 "analysis/sbj_formula/zd_strike_weight.py", "analysis/sbj_formula/x_compare.py",
                 "analysis/sbj_formula/v_execution.py", "src/visualbaseball/plate_decision_v1.py",
                 "web/zone-awareness/index.html", "analysis/zone_decision/README.md",
                 "src/visualbaseball/curated.py", "src/visualbaseball/parser.py"):
        read(path)
    for commit, folder, names in (
        (REVIEWS["초기_ZA"], "analysis/za_review_20261002", ["README.md", "Z-e-draft.md", "checks.json", "check_za.py"]),
        (REVIEWS["APR_ZA"], "analysis/apr_za_review_20261003", ["README.md", "gates.md", "formula_notes.md", "history_notes.md", "verification_plan.md", "results/reproduction.json", "results/height_audit.json"]),
    ):
        for name in names:
            read(f"{folder}/{name}", commit)
    seasons = {}; differences = []; lbs = {}
    for y in range(2019, 2027):
        path = f"data/metrics/zone_awareness/{y}/pitches.parquet"
        present = bool(git("ls-tree", BASE, "--", path).strip())
        lb = js(f"web/data/zone_awareness/{y}/leaderboard.json")
        t = pd.DataFrame(lb["players"]).set_index("batter_id"); t["n"] = t.pitches_seen
        lbs[y] = (lb, t)
        checks = {}
        for name, v, e, meta, level, league in (
            ("apr", "jdv_per_100", "jdv_se", "apr", "league_dv_per_100", "league_jdv_per_100"),
            ("za_plus", "zj_per_100", "zj_se", "za_plus", "league_margin_per_100", "league_zj_per_100"),
        ):
            index, mm = plus(t, v, e, lb[meta][level], lb[meta][league])
            checks[name] = {**mm, "published_k": lb[meta]["shrinkage_k_pitches"],
                            "max_index_error": float(abs(index-t[name]).max()),
                            "pitch_weighted_mean": float(np.average(t[name], weights=t.n))}
            ref = np.sort(index[t.n >= 300]); pct = 100*(np.searchsorted(ref, index, "left")+np.searchsorted(ref, index, "right"))/2/len(ref)
            checks[name]["max_percentile_error"] = float(abs(pct-t["apr_percentile" if name == "apr" else "za_percentile"]).max())
            assert checks[name]["max_index_error"] < 1e-4
            assert checks[name]["max_percentile_error"] < 1e-4
        assert t.qualified_300.equals(t.n >= 300)
        assert int((t.n >= 300).sum()) == lb["qualified_batters"]
        M = lb["za_plus"]["league_margin_per_100"]
        unshrunk = t.zj_per_100 - np.average(t.zj_per_100, weights=t.n)
        unshrunk_index = 100*(M+unshrunk)/M
        diff = (unshrunk_index - t.za_plus)[t.n.between(300, 600)]
        differences.extend(diff.to_list())
        q = t.n >= 300
        seasons[y] = {"parquet_tracked": present, "model_version": lb["model_version"], "players": len(t),
                      "qualified": int(q.sum()), "pitches": int(t.n.sum()), "plus_reproduction": checks,
                      "ZA_no_shrinkage": {"n_300_600_inclusive": len(diff), "mean_absolute": float(abs(diff).mean()),
                                          "rms": float(np.sqrt(np.mean(diff**2))),
                                          "qualified_spearman": float(unshrunk_index[q].corr(t.za_plus[q], method="spearman"))},
                      "B_input_SA": corr(t.jdv_per_100[q], t.swing_aggression[q]),
                      "APR_SA": corr(t.apr[q], t.swing_aggression[q]),
                      "APR_ZA_plus": corr(t.apr[q], t.za_plus[q]),
                      "ZA_raw_SA": corr(t.za_raw[q], t.swing_aggression[q])}
    differences = np.array(differences)
    result["seasons"] = seasons
    result["APR_ZA_plus_mean_season_spearman"] = {
        "all_2019_2026": float(np.mean([s["APR_ZA_plus"]["spearman"] for s in seasons.values()])),
        "human_2019_2023": float(np.mean([seasons[y]["APR_ZA_plus"]["spearman"] for y in range(2019, 2024)])),
        "ABS_2024_2026": float(np.mean([seasons[y]["APR_ZA_plus"]["spearman"] for y in range(2024, 2027)]))}
    result["ZA_shrinkage_removal"] = {"player_seasons": len(differences),
        "season_mean_absolute_simple_average": float(np.mean([s["ZA_no_shrinkage"]["mean_absolute"] for s in seasons.values()])),
        "pooled_mean_absolute": float(np.mean(abs(differences))), "pooled_rms": float(np.sqrt(np.mean(differences**2)))}
    snapshots = {}
    for commit in ("d7bb6fa1", REVIEWS["APR_ZA"]):
        ss = js("data/curated/summary.json", commit)
        diffs = []; peryear = {}
        for y in range(2019, 2027):
            oldlb = js(f"web/data/zone_awareness/{y}/leaderboard.json", commit)
            f = pd.DataFrame(oldlb["players"])
            M = oldlb["za_plus"]["league_margin_per_100"]
            un = 100*(M + f.zj_per_100-np.average(f.zj_per_100, weights=f.pitches_seen))/M
            dif = (un-f.za_plus)[f.pitches_seen.between(300, 600)]
            diffs.extend(dif.to_list())
            peryear[y] = {"model": oldlb["model_version"], "rows": int(f.pitches_seen.sum()),
                          "small_count": len(dif), "mean_absolute": float(abs(dif).mean())}
        ds = np.array(diffs)
        snapshots[commit] = {"generated_at": ss["generated_at"], "curated_date_range_2026": ss["seasons"]["2026"]["date_range"],
                             "player_seasons": len(ds), "pooled_mean_absolute": float(abs(ds).mean()),
                             "pooled_rms": float(np.sqrt(np.mean(ds**2))),
                             "season_mean_absolute_simple_average": float(np.mean([v["mean_absolute"] for v in peryear.values()])),
                             "seasons": peryear}
    result["ZA_historical_snapshots_separate"] = snapshots
    columns = ["game_id", "game_date", "batter_id", "swing", "p_swing", "p_zone", "delta_v", "dv", "judgment", "region"]
    ev = pq.read_table(io.BytesIO(read("data/metrics/zone_awareness/2026/pitches.parquet")), columns=columns).to_pandas()
    ev["batter_id"] = ev.batter_id.astype(str); ev["r"] = ev.swing-ev.p_swing; ev["z"] = 2*ev.p_zone-1
    rows = []; decomposition_errors = []
    for bid, f in ev.groupby("batter_id", sort=True):
        r = f.r.to_numpy(); d = f.delta_v.to_numpy(); z = f.z.to_numpy(); m = r.mean(); mu = d.mean()
        value = 200*(r-m)*d; B = value.mean(); C = B/200; G = f.game_id.nunique()
        old = cluster_se(f, value-B)
        new = cluster_se(f, 200*((r-m)*(d-mu)-C))
        A = 200*r*d; Z = 200*r*z
        de = [np.sum(value[f.region.to_numpy() == reg])/len(f) for reg in ("heart", "shadow_in", "shadow_out", "chase", "waste")]
        decomposition_errors.append(abs(sum(de)-B))
        rows.append({"batter_id": bid, "n": len(f), "G": G, "B": round(float(B), 6),
                     "old_SE": round(old, 6), "IF_SE": round(new, 6),
                     "IF_G_SE": round(new*np.sqrt(G/(G-1)), 6) if G > 1 else np.nan,
                     "A": round(float(A.mean()), 6), "A_SE": round(cluster_se(f, A-A.mean()), 6),
                     "A_unrounded": float(A.mean()), "A_SE_unrounded": cluster_se(f, A-A.mean()),
                     "za_raw": round(float(np.mean(r*z)*100), 6), "zj_per_100": round(float(Z.mean()), 6),
                     "zj_se": round(cluster_se(f, Z-Z.mean()), 6), "SA": round(float(m*100), 6),
                     "zbar": float(z.mean()), "N0": float(100*np.mean((r-m)*z))})
    t = pd.DataFrame(rows).set_index("batter_id"); lb, public = lbs[2026]
    assert set(t.index) == set(public.index)
    cmp = {v: float(abs(t[k]-public[v]).max()) for k, v in (("B", "jdv_per_100"), ("old_SE", "jdv_se"), ("SA", "swing_aggression"), ("za_raw", "za_raw"), ("zj_per_100", "zj_per_100"), ("zj_se", "zj_se"), ("n", "pitches_seen"), ("G", "games_seen"))}
    assert max(cmp.values()) < 1e-6
    L = 100*ev.dv.mean(); league_B = float(np.average(t.B, weights=t.n)); qualified = t.n >= 300
    variants = {}; indices = {}
    for name, val, se in (("B_current", "B", "old_SE"), ("B_IF", "B", "IF_SE"), ("B_IF_G", "B", "IF_G_SE"), ("A", "A", "A_SE"), ("A_unrounded", "A_unrounded", "A_SE_unrounded")):
        idx, mm = plus(t, val, se, L, float(np.average(t[val], weights=t.n)))
        indices[name] = idx
        variants[name] = {**mm, "qualified_APR_SD_ddof1": float(idx[qualified].std()),
                          "qualified_APR_SA": corr(idx[qualified], t.SA[qualified])}
    b0, bi = indices["B_current"], indices["B_IF"]
    residual_mean = ev.r.groupby(ev.batter_id).transform("mean")
    probability = ev.p_swing+residual_mean
    result["pitch_2026"] = {"rows": len(ev), "players": len(t), "qualified": int(qualified.sum()),
        "game_date_min": str(ev.game_date.min()), "game_date_max": str(ev.game_date.max()),
        "games": int(ev.game_id.nunique()), "columns": columns, "null_counts": ev[columns].isna().sum().to_dict(),
        "nonfinite_numeric": int((~np.isfinite(ev[["swing", "p_swing", "p_zone", "delta_v", "dv", "judgment"]].to_numpy())).sum()),
        "public_max_abs_errors": cmp, "region_additivity_max_error": float(max(decomposition_errors)),
        "probability_shift_outside_0_1_fraction": float(((probability < 0) | (probability > 1)).mean()),
        "judgment_identity_max_error": float(abs(ev.judgment-ev.r*ev.z).max()),
        "dv_identity_max_error": float(abs(ev.dv-(2*ev.swing-1)*ev.delta_v).max()),
        "L": float(L), "league_B_from_rounded_players": league_B,
        "current_APR_public_max_error": float(abs(b0-public.apr).max()),
        "current_IF_SE_median_ratio_qualified": float((t.old_SE[qualified]/t.IF_SE[qualified]).median()),
        "current_SE_below_IF_count_qualified": int((t.old_SE[qualified] < t.IF_SE[qualified]).sum()),
        "SE_variants": variants, "B_IF_rank_spearman_qualified": float(b0[qualified].corr(bi[qualified], method="spearman")),
        "B_IF_max_APR_change_qualified": float(abs(bi-b0)[qualified].max()),
        "B_SA_raw": corr(t.B[qualified], t.SA[qualified]),
        "ZA_N0_SA": {"Z0": corr(t.za_raw[qualified], t.SA[qualified]), "N0": corr(t.N0[qualified], t.SA[qualified])},
        "N0_identity_max_error": float(abs(t.N0-(t.za_raw-t.SA*t.zbar)).max())}
    assert len(ev) == report["pitches"] == int(public.n.sum())
    assert summary["seasons"]["2026"]["tables"]["pitches"]["rows"] - report["source"]["excluded"]["invalid_state_location_action_or_identity"] == len(ev)
    assert result["pitch_2026"]["current_APR_public_max_error"] < 1e-6
    assert result["pitch_2026"]["region_additivity_max_error"] < 1e-10
    history = {}
    for y in range(2019, 2027):
        zz = pd.read_csv(io.BytesIO(read(f"analysis/sbj_formula/results/zb_neutral_za_{y}.csv")), dtype={"batter_id": str}).set_index("batter_id")
        history[y] = {"n": len(zz), "N0_N1_spearman": float(zz.N0.corr(zz.N1, method="spearman")),
                      "N0_N1_max_rank_shift": float(abs(zz.N0.rank()-zz.N1.rank()).max()),
                      "Z0_SA_spearman": float(zz.Z0.corr(zz.sa, method="spearman")),
                      "N0_SA_spearman": float(zz.N0.corr(zz.sa, method="spearman"))}
    result["historical_CSV_separate_sample"] = history
    recorded = {}
    for tag in ("zb_neutral_za", "zb_neutral_za_recenter", "zb_neutral_za_strike", "x_compare", "p_count_free"):
        doc = js(f"analysis/sbj_formula/results/{tag}.json")
        # 외부 비공개 대조에서 나온 수치는 출력하지 않는다.
        recorded[tag] = {"recommended": doc.get("recommended_zd", doc.get("recommended")),
                         "interpretation": "저장 기록 열람. 원자료 없는 과거 성능의 독립 재현이 아님"}
        if "candidates" in doc:
            allowed = ("ZG1_reliability", "ZG2_max_abs_sa", "ZG3_max_abs_league_mean", "ZG5_next_bb_pct", "ZG6_x4", "ZG6_x4_ci95", "ZG6_year_to_year", "X1_mean", "X2_max_abs", "X3_next_season", "X4_std_coef_given_iso", "X4_ci95", "X5_year_to_year")
            recorded[tag]["non_external_fields"] = {k: {f: v[f] for f in allowed if f in v} for k, v in doc["candidates"].items()}
    result["historical_recorded_results"] = recorded
    result["limitations"] = ["2019–2025 판단 투구 parquet이 Git에 없어 경기 교차항·SE·반분·재적합 미재현",
                             "외부 비공개 원자료 미사용·수치 미출력, 외부 게이트 독립 검증 불가",
                             "신규 후보 적합·성능 실험·부트스트랩 포함률 실험 미실행",
                             "SE 변경은 예측 고정·리그 기준 및 수축 모수 불확실성 미포함",
                             "parquet에는 별도 모형 버전 메타데이터 없음; 원점수·SE·건수 일치로 현재 집계와 정합 확인"]
    result["inputs"] = INPUTS
    (OUT/"checks.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+"\n")
    t.to_csv(OUT/"player-checks-2026.csv", float_format="%.10f")
    print(json.dumps({"pitch_2026": result["pitch_2026"], "ZA_shrinkage_removal": result["ZA_shrinkage_removal"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
