"""ZA 읽기 전용 교차검증. 신규 후보의 성능은 계산하지 않는다.

저장소 루트에서 PYTHONPATH=src, OMP_NUM_THREADS=2로 실행한다.
REF의 정확한 Git 객체를 읽으며, 체크아웃의 이전 투구 캐시는 쓰지 않는다.
"""
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

REF = "f0dc0a44367852cc1aea86d8eb24dcdb1a19d413"
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent / "checks.json"
HASHES = {}


def blob(path):
    value = subprocess.check_output(["git", "show", f"{REF}:{path}"], cwd=ROOT)
    HASHES[path] = hashlib.sha256(value).hexdigest()
    return value


def load_json(path):
    return json.loads(blob(path))


def load_csv(path):
    return pd.read_csv(io.BytesIO(blob(path)), dtype={"batter_id": str}).set_index("batter_id")


def rho(a, b):
    return float(a.corr(b, method="spearman"))


# Read the required manifests before selecting inputs. No data glob/index reads.
summary = load_json("data/curated/summary.json")
schema = load_json("data/curated/schema.json")
versions = {k: importlib.metadata.version(k) for k in
            ("numpy", "pandas", "pyarrow", "scikit-learn", "scipy", "openpyxl")}
for line in blob("constraints-za.txt").decode().splitlines():
    if "==" in line:
        name, version = line.split("==")
        assert versions[name] == version, (name, versions[name], version)
assert os.environ.get("OMP_NUM_THREADS") == "2"


# Exact algebra checks plus a soft-zone ranking reversal, independent of harness.
rng = np.random.default_rng(20261002)
r = rng.uniform(-1, 1, 100)
z = rng.choice([-1.0, 1.0], 100)
x = r - r.mean()
for c in (1.0, 1.67, 3.0):
    alpha, beta = (1 + c) / 2, (1 - c) / 2
    w = np.where(z >= 0, 1, c)
    assert np.allclose(np.mean(w * x * z), alpha * np.mean(x * z))
    assert np.allclose(np.mean(w * r * z), alpha * np.mean(r * z) + beta * r.mean())
soft_x = np.array([0.5, -0.5])
soft_z = [np.array([0.9, -0.1]), np.array([0.4, -0.4])]
soft_scores = {}
for c in (1.0, 3.0):
    alpha, beta = (1 + c) / 2, (1 - c) / 2
    soft_scores[c] = []
    for zz in soft_z:
        value = np.mean(np.where(zz >= 0, 1, c) * soft_x * zz)
        assert np.allclose(value, alpha * np.mean(soft_x * zz) + beta * np.mean(soft_x * np.abs(zz)))
        soft_scores[c].append(float(value))
assert soft_scores[1.0][0] > soft_scores[1.0][1]
assert soft_scores[3.0][0] < soft_scores[3.0][1]

base = "analysis/sbj_formula/results/"
recenter_json = load_json(base + "zb_neutral_za_recenter.json")
strike_json = load_json(base + "zb_neutral_za_strike.json")
seasons = {}
frames = {}
for year in range(2019, 2027):
    raw = load_csv(base + f"zb_neutral_za_{year}.csv")
    rec = load_csv(base + f"zb_neutral_za_recenter_{year}.csv")
    strike = load_csv(base + f"zb_neutral_za_strike_{year}.csv")
    lb = load_json(f"web/data/zone_awareness/{year}/leaderboard.json")
    assert lb["model_version"] == "za7.6-apr", (year, lb["model_version"])
    public = pd.DataFrame(lb["players"]).assign(batter_id=lambda d: d.batter_id.astype(str)).set_index("batter_id")
    assert set(raw.index) == set(rec.index) == set(strike.index)
    assert set(raw.index) == set(public.index[public.pitches_seen >= 300])
    public = public.loc[raw.index]
    candidates = rec.copy()
    candidates["N5"] = strike.N5
    frames[year] = candidates
    sa = {c: rho(candidates[c], candidates.sa) for c in ("Z0", "N0", "N1", "N2", "N3", "N4", "N5")}
    apr = {c: rho(candidates[c], public.apr) for c in sa}
    # Raw Z0 and SA are compared with unrounded public 6-decimal fields.
    za_error = float((raw.Z0 - public.za_raw).abs().max())
    sa_error = float((raw.sa - public.swing_aggression).abs().max())
    assert za_error <= 0.000051 and sa_error <= 0.000051, (year, za_error, sa_error)
    # Centring should be one season-wide constant. CSV has four decimal rounding.
    shift_spread = {c: float((rec[c] - raw[c]).max() - (rec[c] - raw[c]).min()) for c in raw.columns if c.startswith(("Z", "N"))}
    assert max(shift_spread.values()) <= 0.000201
    # Infer mean(z) from the exact production identity N0_raw=Z0_raw-SA*mean(z).
    # Exclude very small SA to bound error from four-decimal CSV rounding.
    g = raw.loc[raw.sa.abs() >= 0.2].copy()
    zbar = (g.Z0 - g.N0) / g.sa
    assert zbar.abs().max() <= 1.002
    correction = g.N0 - g.Z0
    common = -zbar.mean() * g.sa
    composition = correction - common
    cov_sa = float(np.cov(g.sa, g.sa, ddof=0)[0, 1])
    slopes = {"total": float(np.cov(correction, g.sa, ddof=0)[0, 1] / cov_sa),
              "common_zone_mean": float(np.cov(common, g.sa, ddof=0)[0, 1] / cov_sa),
              "player_composition_remainder": float(np.cov(composition, g.sa, ddof=0)[0, 1] / cov_sa)}
    assert abs(slopes["total"] - slopes["common_zone_mean"] - slopes["player_composition_remainder"]) < 1e-12
    q = public.pitches_seen.to_numpy()
    seasons[year] = {"qualified": len(raw), "spearman_sa": sa, "spearman_apr": apr,
                     "N0_N1_spearman": rho(rec.N0, rec.N1), "N0_N1_rank_changes": int((rec.N0.rank() != rec.N1.rank()).sum()),
                     "N0_N1_max_rank_shift": float((rec.N0.rank() - rec.N1.rank()).abs().max()),
                     "Z0_public_max_error": za_error, "SA_public_max_error": sa_error,
                     "recenter_shift_spread": shift_spread, "zbar_inferred_n": len(g),
                     "zbar_inferred_quantiles": {str(p): float(zbar.quantile(p)) for p in (0.1, 0.5, 0.9)},
                     "zbar_inferred_negative_fraction": float((zbar < 0).mean()),
                     "correction_SA_pearson": float(correction.corr(g.sa)), "correction_slopes": slopes,
                     "N3_weights": recenter_json["seasons"][str(year)]["weights"]["N3"]}

mean_apr = {c: float(np.mean([v["spearman_apr"][c] for v in seasons.values()])) for c in seasons[2019]["spearman_apr"]}
era_apr = {era: {c: float(np.mean([seasons[y]["spearman_apr"][c] for y in ys])) for c in mean_apr}
           for era, ys in {"umpire_2019_2023": range(2019, 2024), "ABS_2024_2026": range(2024, 2027)}.items()}
agreement = {}
for c in ("Z0", "N4", "N5"):
    agreement[c] = max(abs(seasons[y]["spearman_apr"][c] - strike_json["ZG7_spearman_apr"][c][str(y)]) for y in seasons)
    assert agreement[c] < 0.0001

result = {"ref": REF, "python": f"{sys.version_info.major}.{sys.version_info.minor}", "versions": versions,
          "environment": {"PYTHONPATH": os.environ.get("PYTHONPATH"), "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS")},
          "summary_generated_at": summary["generated_at"], "schema_sha256": schema["schema_sha256"],
          "tests": {"binary_neutral_identity": True, "binary_SA_mixture": True,
                    "continuous_identity": True, "soft_zone_rank_reversal": soft_scores,
                    "public_score_agreement": True, "recenter_constant": True},
          "seasons": seasons, "mean_apr": mean_apr,
          "era_mean_apr": era_apr, "recorded_APR_correlation_max_error": agreement,
          "source_sha256": HASHES,
          "limits": ["후보 CSV는 소수 넷째 자리, 공개 점수는 소수 여섯째 자리다.",
                     "za7.6-apr 투구 캐시가 없어 투구별 재현 및 반분 재계산은 하지 않았다.",
                     "외부 ZJ 원자료가 없어 ZG4를 새로 검증하지 않았다.",
                     "신규 후보의 성능은 계산하지 않았다."]}
OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
receipt = {"schemaVersion": 1, "items": [
    {"id": "zone-algebra", "title": "존 밖 가중의 대수와 운영 정의", "queries": [{
        "id": "formula-source", "source": {"label": "요청 브랜치의 산식과 운영 소스",
            "files": [{"label": p} for p in ("gates.md", "zb_neutral_za.py", "zd_strike_weight.py", "zone_decision.py")],
            "caveats": ["이진 존 근사와 연속 판정 확률은 서로 다른 대수식을 갖는다."],
            "evidenceFlow": [{"kind": "validation", "title": "직접 계산 결과",
                "detail": "이진 중립 항등식, SA 혼합식, 연속 분해식의 assert가 통과했다. 연속값 반례에서 c=1은 A>B, c=3은 A<B였다."}]},
        "methods": [{"language": "calculation", "code": "N0 = 100 E[(r-m)z]\nNc = 100 [((1+c)/2) E[(r-m)z] + ((1-c)/2) E[(r-m)|z|]] / E_league[w]"}]}]},
    {"id": "apr-overlap", "title": "APR과의 겹침을 새로 계산한 결과", "queries": [{
        "id": "candidate-public-join", "source": {"label": "후보 CSV와 공개 리더보드",
            "files": [{"label": "zb_neutral_za_recenter_2019.csv"}, {"label": "zb_neutral_za_strike_2019.csv"},
                      {"label": "zb_neutral_za_strike.json"}, {"label": "leaderboard.json"}],
            "metricDefinitions": [{"label": "APR 순위 상관", "definition": "APR 순위 상관은 시즌별 적격 타자의 후보와 공개 APR 간 Spearman 상관이다."}],
            "filters": ["시즌: 2019–2026", "적격: 300구 이상", "커밋: f0dc0a44367852cc1aea86d8eb24dcdb1a19d413"],
            "caveats": result["limits"][:3],
            "evidenceFlow": [{"kind": "validation", "title": "서로 다른 산출물 대조",
                "detail": "8개 시즌의 적격 타자 ID 집합이 같았다. 후보 원시 Z0 및 SA는 공개 점수와 CSV 반올림 허용폭 0.000051 안에서 일치했다. Z0/N4/N5의 재계산 APR 상관은 저장 JSON과 0.0001 이내에서 일치했다."}]},
        "rows": [{"candidate": c, "all_seasons": mean_apr[c], "umpire": era_apr["umpire_2019_2023"][c], "abs": era_apr["ABS_2024_2026"][c]} for c in mean_apr],
        "columns": [{"field": "candidate", "label": "후보"}, {"field": "all_seasons", "label": "8시즌 평균"},
                    {"field": "umpire", "label": "구심 시즌 평균"}, {"field": "abs", "label": "ABS 시즌 평균"}],
        "preview": {"kind": "aggregate", "note": "시즌별 상관의 단순 평균이며, 타자 자료를 합친 상관은 아니다."}}]},
    {"id": "neutrality", "title": "N0의 SA 상관과 N1 순위 차이", "queries": [{
        "id": "neutral-csv-decomposition", "source": {"label": "원시·재중심화 후보 CSV",
            "files": [{"label": "zb_neutral_za_2021.csv"}, {"label": "zb_neutral_za_recenter_2021.csv"}],
            "filters": ["시즌: 2019–2026", "적격: 300구 이상"],
            "caveats": ["존 방향 평균은 N0=Z0-SA·평균(z)에서 역산했다. |SA|<0.2인 선수는 반올림 오차 확대를 막기 위해 역산에서 제외했다.",
                        "SA 보정항의 선형 공분산 분해는 Spearman 상관 차이의 직접 분해가 아니다."],
            "evidenceFlow": [{"kind": "validation", "title": "역산과 공분산 분해",
                "detail": "N0와 N1의 Spearman은 0.998496–0.999912였다. 2021 평균 존 방향의 역산 중앙값은 -0.068885였다. 보정항의 SA 기울기는 +0.066703, 공통 평균 성분은 +0.067634, 선수별 구성 잔차는 -0.000931이었다."}]},
        "rows": [{"season": y, "z0_sa": v["spearman_sa"]["Z0"], "n0_sa": v["spearman_sa"]["N0"],
                  "n0_n1": v["N0_N1_spearman"], "rank_shift": v["N0_N1_max_rank_shift"]} for y, v in seasons.items()],
        "columns": [{"field": "season", "label": "시즌"}, {"field": "z0_sa", "label": "Z0–SA 상관"},
                    {"field": "n0_sa", "label": "N0–SA 상관"}, {"field": "n0_n1", "label": "N0–N1 상관"},
                    {"field": "rank_shift", "label": "N0–N1 최대 순위 이동"}],
        "preview": {"kind": "aggregate", "note": "CSV 반올림을 포함한 시즌별 재계산 결과다."}}]}
]}
(Path(__file__).parent / "sources.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"tests": result["tests"], "mean_apr": mean_apr, "era_mean_apr": era_apr,
                  "seasons": {y: {k: v[k] for k in ("qualified", "spearman_sa", "N0_N1_spearman", "N0_N1_max_rank_shift", "zbar_inferred_quantiles", "correction_slopes")} for y, v in seasons.items()},
                  "output": str(OUT)}, ensure_ascii=False, indent=2))
