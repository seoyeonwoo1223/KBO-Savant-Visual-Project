"""확보된 인계·연구의 입력과 라벨을 분리하고 재현용 helper 원판을 묶는다."""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from common import OUT, FF, SI_PHYSICS, EXTRA, sha, save

SOURCE_ROOT = Path("/workspace/KBO-Savant-Visual-Project")
SNAPSHOT = Path("/workspace/eaa-handoff-20261007/unpacked/eaa-continuation-20261007/repo")
ARM = SOURCE_ROOT / "analysis/arm_angle"


def main():
    dest = OUT / "inputs"
    dest.mkdir(exist_ok=True)
    sys.path.insert(0, str(ARM / "conditional_eaa_20261007"))
    # 원래 코드의 순수 입력 helper만 호출하며 이전 save는 호출하지 않는다.
    sys.path[:0] = [str(SNAPSHOT / "src"), str(SNAPSHOT / "analysis/arm_angle"),
                   str(ARM / "primary_pitch_diagnostics_20261007")]
    from pitch_joint_eaa_features import assemble_mlb, assemble_kbo
    from diagnostics import primary_inputs, input_variables

    mlb, stats, source = assemble_mlb()
    mlb = input_variables(primary_inputs(mlb), stats)
    k, ks, _ = assemble_kbo()
    k = input_variables(primary_inputs(k), ks)
    frames = {"MLB": mlb, "KBO_FF100": k}
    for month in ["May", "July"]:
        frames[month] = pd.read_parquet(ARM / f"conditional_eaa_20261007/{month}2025_all_inputs_and_labels.parquet")
    frames["KBO_all"] = pd.read_csv(ARM / "primary_pitch_diagnostics_20261007/KBO2026_primary_and_cluster.csv",
                                    dtype={"pitcher":str}, float_precision="round_trip")
    inputs = {}
    for population, d in frames.items():
        d = d.copy().reset_index(drop=True)
        d["pitcher"] = d.pitcher.astype(str)
        d["row_id"] = population + "-" + d.season.astype(str) + "-" + d.pitcher
        assert d.row_id.is_unique
        for name in EXTRA:
            if "*" in name:
                left, right = name.split("*")
                if left in d and right in d:
                    d[name] = d[left] * d[right]
        fields = ["row_id", "pitcher", "season", "primary", "primary4", "n", "n_ff", "primary_count",
                  "primary_share", "type_SI_count", "name", "outer_fold", "fixed_training_row",
                  "label95", "FF100_evaluation_eligible", "observed_angle_coverage", "ff_ivb_in", "ff_hb_arm_in"]
        fields += FF + SI_PHYSICS + [c for c in EXTRA if c in d]
        fields = list(dict.fromkeys(c for c in fields if c in d))
        d[fields].to_parquet(dest / f"{population}_inputs.parquet", index=False)
        assert "arm_angle" not in fields
        if "arm_angle" in d:
            d[["row_id", "arm_angle"]].to_parquet(dest / f"{population}_targets.parquet", index=False)
        refs = [c for c in ["v1_MLB_direct_component", "v1_MLB_component_outside_domain", "baseline", "name"] if c in d]
        if refs:
            d[["row_id", "pitcher"] + refs].to_parquet(dest / f"{population}_references.parquet", index=False)
        inputs[population] = {"rows": len(d), "players": d.pitcher.nunique(), "inputs_sha256": sha(dest/f"{population}_inputs.parquet")}
    # 과거 full의 재현값만 저장하며 다른 모형을 사후 선택하지 않는다.
    for filename in ["MLB_OOF_predictions.csv", "May2025_reused_predictions.csv", "July2025_reused_predictions.csv", "KBO2026_predictions.csv"]:
        d = pd.read_csv(ARM / "variable_diagnostics_20261007/ablation" / filename,
                        dtype={"pitcher":str}, float_precision="round_trip")
        d[[c for c in ["pitcher", "season", "anchor", "full"] if c in d]].to_parquet(dest/(filename.replace(".csv", "_reference.parquet")), index=False)
    fallback = pd.read_csv(ARM/"primary_pitch_diagnostics_20261007/KBO_SI_FC_fallback_states.csv",dtype={"pitcher":str})
    fallback.to_csv(dest/"KBO_fallback_reference.csv",index=False)

    frozen = {}
    with zipfile.ZipFile(dest/"frozen_helpers.zip", "w", compression=zipfile.ZIP_DEFLATED) as z:
        paths = sorted((SNAPSHOT/"analysis/arm_angle").glob("*.py")) + sorted((SNAPSHOT/"src/visualbaseball").glob("*.py"))
        for path in paths:
            relative = str(path.relative_to(SNAPSHOT))
            info = zipfile.ZipInfo(relative, date_time=(2026,10,7,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info,path.read_bytes())
            frozen[relative] = sha(path)
    manifests = {}
    for name in ["continuation_20261007_research", "primary_pitch_diagnostics_20261007", "conditional_eaa_20261007", "variable_diagnostics_20261007"]:
        path = ARM/name/"RESULTS-MANIFEST.json"
        data = json.loads(path.read_text())
        for relative, entry in data["files"].items(): assert sha(path.parent/relative)==entry["sha256"]
        manifests[name] = {"sha256":sha(path),"files":len(data["files"])}
    save("inputs/source_manifest.json", {"source_scope":"확보된 입력 캐시·월 집계·코드 원판. 전체 과거 원문 아님",
        "inputs":inputs,"prior_manifests":manifests,"original_cache_manifest":source,
        "frozen_helpers_sha256":sha(dest/"frozen_helpers.zip"),"frozen_code":frozen,
        "operational_v3_sha256":sha(SOURCE_ROOT/"data/models/estimated_arm_angle_v3.json"),
        "operational_v1_sha256":sha(SOURCE_ROOT/"data/models/estimated_arm_angle_v1.json"),
        "original_handoff_zip_sha256":sha(Path('/workspace/eaa-handoff-20261007/eaa-continuation-20261007.zip')),
        "raw_historical_full_verified":False,"all_evaluation_periods_reused":True})
    print("INPUTS_PREPARED", {p:v['rows'] for p,v in inputs.items()})


if __name__ == "__main__":
    main()
