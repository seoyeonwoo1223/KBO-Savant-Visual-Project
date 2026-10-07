"""등록 외 기술 통계: FF 앵커 11열의 KBO 2026 입력 분포를 MLB 학습 캐시와 비교한다. 라벨·KBO 참고각도는 쓰지 않는다."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "sinker_anchor_20261007"))
from common import FF, load  # noqa: E402

h, k = load("MLB"), load("KBO_all")
k = k.loc[k.n_ff.ge(100) & np.isfinite(k[FF]).all(axis=1)]
rows = []
for c in FF + ["ff_ivb_in", "ff_hb_arm_in"]:
    m, x = h[c].to_numpy(float), k[c].to_numpy(float)
    lo, hi = np.quantile(m, [.01, .99])
    rows.append({"feature": c, "KBO_rows": len(x), "MLB_median": np.median(m), "KBO_median": np.median(x),
                 "median_shift_in_MLB_sd": (np.median(x)-np.median(m))/m.std(),
                 "KBO_below_MLB_q01": float((x < lo).mean()), "KBO_above_MLB_q99": float((x > hi).mean())})
pd.DataFrame(rows).to_csv(HERE / "KBO_FF_input_shift.csv", index=False)
print(pd.DataFrame(rows).round(3).to_string())

# 고정 FF 앵커(전체 MLB 학습)의 KBO 예측이 범위 밖 입력의 MLB 1–99분위 절단에 얼마나 반응하는지(라벨 없음, 기계적 민감도)
from common import legacy_helpers  # noqa: E402
ridge_fit = legacy_helpers()[0]
hl = load("MLB", labelled=True)
model = ridge_fit(hl, FF)
base = model.predict(k[FF].to_numpy(float))
sens = {}
for cols in [["ff_movement_size_m"], ["ff_flight55_to_plate"], ["ff_speed55"], ["height_m"],
             ["ff_movement_size_m", "ff_flight55_to_plate", "ff_speed55", "height_m"], FF]:
    x = k[FF].copy()
    for c in cols:
        lo, hi = np.quantile(hl[c], [.01, .99]); x[c] = x[c].clip(lo, hi)
    delta = model.predict(x.to_numpy(float)) - base
    changed = np.abs(delta) > 1e-9
    sens["+".join(cols) if cols != FF else "all_FF11"] = {"rows_changed": int(changed.sum()), "mean_delta_all": float(delta.mean()),
        "mean_delta_changed": float(delta[changed].mean()) if changed.any() else 0.0,
        "q10_50_90_changed": np.quantile(delta[changed], [.1, .5, .9]).tolist() if changed.any() else None}
import json  # noqa: E402
(HERE / "KBO_clip_sensitivity.json").write_text(json.dumps({"rows": len(k), "model": "FF anchor fixed on all MLB 2295 rows",
    "KBO_reference_angles_used": False, "registered": False, "sensitivity": sens}, ensure_ascii=False, indent=2) + "\n")
for name, s in sens.items(): print(name, s["rows_changed"], round(s["mean_delta_all"], 3), round(s["mean_delta_changed"], 3), np.round(s["q10_50_90_changed"] or [], 2))
