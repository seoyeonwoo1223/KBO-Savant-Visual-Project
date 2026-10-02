"""보조 진단 (사전 등록 아님): J5 외부 타당성을 시즌 안에서 중심화해 다시 계산한다.

gates.md J5는 7개 시즌 쌍을 그대로 합쳐 상관을 구했다. 지표와 결과 비율의 리그 수준이 시즌마다 다르면
시즌 간 차이가 상관에 섞인다. 여기서는 지표(시즌 t)와 결과(같은 시즌 또는 t+1)를 각 시즌 쌍 안에서
평균 0으로 맞춘 뒤 합친다. 결과: results/jdv_j5_centered.json
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import jdv_experiment as J  # noqa: E402

tables, outs = {}, {}
for y in J.SEASONS:
    df = J.evidence(y)
    per = {k: J.per_batter(df, k) for k in J.METRICS}
    q = per["jdv"].index[per["jdv"].n >= J.QUAL]
    tables[y] = pd.DataFrame({k: per[k].score[q] for k in J.METRICS}); outs[y] = J.outcomes(y)
cols = ["bb_pct", "k_pct", "obp", "hr_pct"]
res = {"season_means": {}}
for name, lag in (("same_season", 0), ("next_season", 1)):
    frames = []
    for y in J.SEASONS:
        if y + lag not in tables:
            continue
        ids = tables[y].index if lag == 0 else tables[y].index.intersection(tables[y + 1].index)
        f = tables[y].loc[ids].join(outs[y + lag], how="inner")
        if lag == 0:
            res["season_means"][y] = {k: float(f[k].mean()) for k in list(J.METRICS) + cols}
        frames.append(f - f.mean())
    allf = pd.concat(frames)
    res[name] = {"batter_seasons": len(allf), **{k: {c: float(allf[k].corr(allf[c])) for c in cols} for k in J.METRICS}}
(Path(__file__).with_name("results") / "jdv_j5_centered.json").write_text(json.dumps(res, indent=1) + "\n")
for name in ("same_season", "next_season"):
    print(name, {k: {c: round(v, 3) for c, v in res[name][k].items()} for k in J.METRICS})
print({y: {k: round(v, 3) for k, v in m.items()} for y, m in res["season_means"].items()})
